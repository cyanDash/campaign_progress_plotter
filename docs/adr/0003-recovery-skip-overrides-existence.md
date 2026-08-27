# Progress ≥98% overrides a confirmed recovery dataset

Production policy: no recovery campaign is run once progress reaches 98% of
target. `recovery_skipped()` (in `campaign_projection.py`) checks this and,
when true, takes priority over `recovery_confirmed` (whether a
`recovery_campaign` dataset exists in SAM) — the recovery portion isn't
plotted even if a recovery dataset exists.

This looks backwards at first read: why ignore evidence that recovery
started? Because a recovery dataset's existence in SAM is not proof recovery
actually ran. This happened for real: a recovery campaign was submitted (so
its dataset was created), the grid never processed the jobs, and it was
canceled — by the time progress crossed 98% anyway (through the main
campaign's own trickle-in, not the canceled recovery), the stale recovery
dataset was still sitting in SAM. Trusting existence alone would have kept
showing a recovery phase that never happened.
