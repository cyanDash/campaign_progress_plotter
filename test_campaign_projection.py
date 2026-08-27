"""Tests for campaign_projection.py.

These exercise the full prediction logic (all three cases, the recovery-skip
threshold, the failed-files calculation) using synthetic finished-file lists --
no SAM, no live grid, no subprocess calls. Run with: pytest
"""

from datetime import date, datetime, timezone

from campaign_projection import project_campaign, recovery_skipped


def utc(y, m, d, hour=0):
    return datetime(y, m, d, hour, tzinfo=timezone.utc)


def test_recovery_skipped_threshold():
    assert recovery_skipped(980, 1000) is True   # exactly 98%
    assert recovery_skipped(979, 1000) is False  # just under
    assert recovery_skipped(1000, 1000) is True  # fully done
    assert recovery_skipped(100, 0) is False      # no target -> never skip


def test_case0_recovery_skipped_ends_next_day():
    # Progress crosses 98% today, but hasn't hit 100% -- ends tomorrow, no recovery line.
    finished = [10, 50, 90, 98]
    start_date = date(2026, 1, 1)
    today_idx = 3
    today_date = date(2026, 1, 4)

    projection = project_campaign(
        finished, target=100, start_date=start_date,
        today_idx=today_idx, today_date=today_date, now=utc(2026, 1, 4, 12),
        campaign_start_dt=utc(2026, 1, 1), recovery_start_date=None, recovery_start_dt=None,
    )

    assert projection.end_date == date(2026, 1, 5)
    assert projection.recovery_idx is None
    assert projection.show_recovery_line is False
    assert projection.show_end_date_annotation is True
    assert projection.end_date_label == "Predicted End Date: 5-Jan"
    assert projection.failed_files == 0  # not at the end date yet
    assert max(projection.projected) <= 100  # capped at target


def test_case0_recovery_skipped_already_complete():
    # Progress already hit 100% -- ends today, not tomorrow.
    finished = [10, 50, 90, 100]
    start_date = date(2026, 1, 1)

    projection = project_campaign(
        finished, target=100, start_date=start_date,
        today_idx=3, today_date=date(2026, 1, 4), now=utc(2026, 1, 4, 12),
        campaign_start_dt=utc(2026, 1, 1), recovery_start_date=None, recovery_start_dt=None,
    )

    assert projection.end_date == date(2026, 1, 4)
    assert projection.show_recovery_line is False
    assert projection.failed_files == 0  # hit target exactly, nothing failed


def test_case1_recovery_not_started_predicts_start_date():
    # Progress is nowhere near the skip threshold and no recovery dataset exists yet
    # -- predicts when recovery will need to start, not an end date.
    finished = [10, 30, 55]
    start_date = date(2026, 1, 1)

    projection = project_campaign(
        finished, target=1000, start_date=start_date,
        today_idx=2, today_date=date(2026, 1, 3), now=utc(2026, 1, 3),
        campaign_start_dt=utc(2026, 1, 1), recovery_start_date=None, recovery_start_dt=None,
    )

    assert projection.show_recovery_line is True
    assert projection.recovery_line_label.startswith("Predicted Recovery Start:")
    assert projection.show_end_date_annotation is False  # only a start date is predicted, not an end date
    assert projection.recovery_idx == (projection.end_date - start_date).days
    assert projection.projected[-1] == 1000  # capped at target once the projection reaches it


def test_case2_recovery_confirmed_predicts_end_date_and_failed_files():
    # Recovery is confirmed underway; the predicted end date lands on "today", and
    # the campaign falls short of target on that day.
    finished = [10, 40, 60, 90]
    start_date = date(2026, 1, 1)
    recovery_start_date = date(2026, 1, 3)  # recovery_idx = 2

    projection = project_campaign(
        finished, target=100, start_date=start_date,
        today_idx=3, today_date=date(2026, 1, 4), now=utc(2026, 1, 4),
        campaign_start_dt=utc(2026, 1, 1),
        recovery_start_date=recovery_start_date, recovery_start_dt=utc(2026, 1, 3),
    )

    assert projection.recovery_idx == 2
    assert projection.show_recovery_line is True
    assert projection.recovery_line_label == "Recovery Start: 3-Jan"
    assert projection.end_date == date(2026, 1, 4)
    assert projection.show_end_date_annotation is True
    assert projection.failed_files == 10  # target 100, finished 90 on the end date
    assert projection.projected == [10, 40, 70, 100]
