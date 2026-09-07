"""Campaign projection -- predicts a campaign's trajectory (recovery start date,
or end date) from its daily finished-file history.

Pure: no SAM I/O, no plotting. Everything here is plain data in, plain data out,
so it can be tested with synthetic finished-file lists instead of a live grid.
"""

import math
from dataclasses import dataclass
from datetime import timedelta

RECOVERY_SKIP_THRESHOLD = 0.98  # Production policy: no recovery campaign is run once progress reaches this fraction of target.
MAX_PROJECTION_DAYS = 3650  # Safety cap so a stalled/zero rate can't loop forever.


def format_date(d):
    """Format date as '6-May'. Takes a datetime.date object and returns a string."""
    return f"{d.day}-{d.strftime('%b')}"


def get_date_range(start, end):
    """Return list of formatted date labels from start..end inclusive.

    Works across month and year boundaries.
    """
    if start > end:
        return []
    days = (end - start).days
    return [format_date(start + timedelta(days=i)) for i in range(days + 1)]


def recovery_skipped(finished_count, target):
    """Whether progress is already far enough along that, per policy, no (further)
    recovery campaign will be run -- regardless of whether a recovery_campaign
    dataset exists in SAM (it may have been submitted, then canceled because the
    grid never picked the jobs up, so its mere existence isn't proof recovery
    happened). Callers collecting daily counts from SAM use this same predicate to
    know when they can stop querying."""
    return bool(target) and finished_count / target >= RECOVERY_SKIP_THRESHOLD


@dataclass
class Projection:
    dates: list
    projected: list
    today_idx: int
    today_date: object  # datetime.date
    end_date: object  # datetime.date
    recovery_idx: object  # int or None
    show_recovery_line: bool
    recovery_line_label: object  # str or None
    end_date_label: str
    show_end_date_annotation: bool
    failed_files: int


def project_campaign(finished, target, start_date, today_idx, today_date, now,
                      campaign_start_dt, recovery_start_date, recovery_start_dt):
    """Predict the campaign's trajectory from its daily finished-file history.

    `finished` is the cumulative finished-file count for each day from start_date
    through today_date inclusive; `today_idx`/`today_date` must correspond to its
    last entry (a caller that stopped collecting early -- e.g. once
    `recovery_skipped()` was already True -- passes that earlier day as "today").

    `recovery_start_date`/`recovery_start_dt` are None if no recovery_campaign
    dataset exists yet in SAM.
    """
    elapsed_days = (now - campaign_start_dt).total_seconds() / 86400
    current_avg_rate = finished[today_idx] / elapsed_days if elapsed_days > 0 else 0

    recovery_confirmed = recovery_start_date is not None
    progress_ratio = finished[today_idx] / target if target else 0
    skipped = progress_ratio >= RECOVERY_SKIP_THRESHOLD

    if skipped:
        # Case 0: progress is at/above the policy threshold -- no recovery portion to
        # plot. The campaign is considered to end the next day (or today, if already
        # fully done).
        end_date = today_date if progress_ratio >= 1.0 else today_date + timedelta(days=1)
        dates = get_date_range(start_date, end_date)

        projected = [finished[0]]
        for i in range(1, len(dates)):
            if i < today_idx:
                avg_rate = (finished[i] - finished[0]) / i
            else:
                avg_rate = current_avg_rate
            # Cap at target -- once reached, the projection shouldn't keep climbing past it.
            projected.append(min(projected[-1] + avg_rate, target))

        recovery_idx = None

    elif not recovery_confirmed:
        # Case 1: Recovery has not started yet. Each day, calculate average rate up
        # to that day and project forward until the target is reached at the current
        # rate -- that's our estimate of when recovery will kick in.
        projected = [finished[0]]
        i = 1
        while projected[-1] < target and i <= MAX_PROJECTION_DAYS:
            if i < today_idx:
                avg_rate = (finished[i] - finished[0]) / i
            else:
                avg_rate = current_avg_rate
            if avg_rate <= 0:
                print("Warning: progress rate is zero or negative, cannot predict recovery start date.")
                break
            projected.append(projected[-1] + avg_rate)
            i += 1
        projected[-1] = min(projected[-1], target)

        recovery_idx = len(projected) - 1
        recovery_start_date = start_date + timedelta(days=recovery_idx)
        end_date = recovery_start_date

        dates = get_date_range(start_date, end_date)

    else:
        # Case 2: Recovery has already started -- predict the campaign end date from
        # the rate of progress since recovery began.
        assert recovery_start_date <= today_date, "recovery_start_date must be on or before today_date"
        recovery_idx = (recovery_start_date - start_date).days
        recovery_target = target - finished[recovery_idx - 1]

        elapsed_recovery_days = (now - recovery_start_dt).total_seconds() / 86400
        if elapsed_recovery_days > 0:
            recovery_rate = (finished[today_idx] - finished[recovery_idx - 1]) / elapsed_recovery_days
        else:
            recovery_rate = current_avg_rate
        if recovery_rate <= 0:
            recovery_rate = current_avg_rate

        post_recovery_days = max(1, math.ceil(recovery_target / recovery_rate)) if recovery_rate > 0 else 1
        end_date = start_date + timedelta(days=recovery_idx - 1) + timedelta(days=post_recovery_days)

        dates = get_date_range(start_date, end_date)

        projected = [0] * len(dates)
        projected[0] = finished[0]

        for i in range(1, recovery_idx):
            if i <= today_idx:
                avg_rate = (finished[i] - finished[0]) / i
            else:
                avg_rate = current_avg_rate
            projected[i] = projected[i - 1] + avg_rate

        start_val = projected[recovery_idx - 1]
        recovery_target_amount = target - start_val
        for j in range(post_recovery_days):
            idx = recovery_idx + j
            if idx < len(dates):
                projected[idx] = start_val + recovery_target_amount * (j + 1) / post_recovery_days

    # Today's date is capped at the (now predicted) campaign end date to avoid
    # out-of-range indices.
    today_date = min(today_date, end_date)
    today_idx = (today_date - start_date).days

    show_recovery_line = recovery_idx is not None
    recovery_line_label = None
    if show_recovery_line:
        recovery_line_label = (
            f"Recovery Start: {format_date(recovery_start_date)}" if recovery_confirmed
            else f"Predicted Recovery Start: {format_date(recovery_start_date)}"
        )
    end_date_label = f"Predicted End Date: {format_date(end_date)}"
    show_end_date_annotation = recovery_confirmed or skipped

    failed_files = 0
    if today_date == end_date and target > finished[today_idx]:
        failed_files = target - finished[today_idx]

    return Projection(
        dates=dates,
        projected=projected,
        today_idx=today_idx,
        today_date=today_date,
        end_date=end_date,
        recovery_idx=recovery_idx,
        show_recovery_line=show_recovery_line,
        recovery_line_label=recovery_line_label,
        end_date_label=end_date_label,
        show_end_date_annotation=show_end_date_annotation,
        failed_files=failed_files,
    )
