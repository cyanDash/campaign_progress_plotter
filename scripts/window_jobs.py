"""window_jobs -- which Submissions ran each plotted window, from the State
File of poms_auto_submit (branch new-split-window): the slice from its
`window_launches` section, the recovery from `window_recovery`, and their
jobsub ids from the `submissions` cache. Everything is keyed by the window's
start as unix seconds (UTC), the `firsttime` of its cs_split_type.
"""

import json
import re

# The window's SAM definition name ends with its first and last input time.
WINDOW_TIMES = re.compile(r"_time_(\d+)__(\d+)$")


def _read(path):
    try:
        with open(path) as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return state if isinstance(state, dict) else {}


def window_submissions(state_path, bounds):
    """{window start: [{kind, submission_id, jobsub_job_id}]} for the windows
    in `bounds` (UTC (start, end) pairs) that have a recorded Submission, the
    slice first. jobsub_job_id is None when the cache does not know the id.
    Missing or unreadable state gives {}."""
    state = _read(state_path)
    cache = state.get("submissions") or {}
    wanted = {int(start.timestamp()) for start, _ in bounds}
    found = {}

    def add(epoch, kind, submission_id):
        if epoch in wanted and submission_id is not None:
            jobsub = (cache.get(str(submission_id)) or {}).get("jobsub_job_id")
            found.setdefault(epoch, []).append(
                {"kind": kind, "submission_id": str(submission_id), "jobsub_job_id": jobsub})

    for epoch, record in (state.get("window_launches") or {}).items():
        add(int(epoch), "slice", (record or {}).get("submission_id"))
    for window, record in (state.get("window_recovery") or {}).items():
        match = WINDOW_TIMES.search(window)
        if match:
            add(int(match.group(1)), "recovery", (record or {}).get("submission_id"))
    return found


def latest_limits(workers, kind):
    """(memory request in MB, wall-time limit in hours) of the newest Submission
    of `kind` ('slice' or 'recovery') among `workers`, each tagged with `kind`
    and `submission_id`: the value most of its workers carry, None when it has
    none. Newest is the highest submission id, so a limit changed during the
    week shows the current one."""
    group = [w for w in workers if w.get("kind", "slice") == kind]
    if not group:
        return None, None
    newest = max(int(w.get("submission_id") or 0) for w in group)
    latest = [w for w in group if int(w.get("submission_id") or 0) == newest]

    def common(key):
        values = [w[key] for w in latest if w.get(key) is not None]
        return max(set(values), key=values.count) if values else None
    return common("request_mb"), common("limit_h")
