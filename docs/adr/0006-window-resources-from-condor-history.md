# Plot worker exit status, memory and wall time from condor

## Context

The window plot (branch `auto-run3-data`) shows how many input files lack an
output ("missing n") but not why. The answer is in condor: exit code, peak
memory and wall time of each worker of the window's slice and recovery
Submissions (bad node, memory hold, 12 h limit, late workers).

## Decision

`window_output_plotter.py` draws a 3x1 report: the bar chart, then peak
memory (1 GB bins) and wall time (1 h bins) of every worker of the plotted
windows, stacked by exit 0 / non-zero / still running. The weekly plot pools
its 7 windows into the two histograms.

- **Which Submissions.** `window_jobs.py` reads poms_auto_submit's State File
  (branch `new-split-window`): `window_launches` (slice, ADR-0026 there) and
  `window_recovery`, joined to the window by its start in unix seconds, and
  `submissions` for the jobsub id. The checkout is `$POMS_AUTO_SUBMIT_DIR`,
  which `setup.sh` defaults to `../poms_auto_submit` and checks exists.
- **Condor seam.** `condor_fetcher.py` runs `condor_history` (finished
  workers) and `condor_q` (running ones, memory only) on the DAG's schedd, as
  `samweb_fetcher.py` does for SAM. `setup.sh` fetches the same managed
  token poms_auto_submit uses.
- **Batched, parallel, cached.** `condor_history` scans the schedd's whole
  history (about 52 s per call), so every DAG of one schedd goes in one
  `condor_history` and one `condor_q` call, and up to 4 calls run at once.
  A DAG with nothing left in the queue is finished: its worker rows are kept
  in `cache/condor_workers.json` (git-ignored) and never fetched again. Cold,
  a daily plot takes 54 s and a 2-window weekly 55 s; with the cache warm
  1-2 s. Before batching they took 106 s and 215 s.
- **Soft failure.** No State File, no recorded Submission, no token or a
  condor error leaves the histograms out; the bar chart is still written and
  the missing Submission is printed.

## Consequences

- condor history is short: jobsub01's oldest record was 2026-11-01 on
  2026-11-17 (about 16 days). A 7-day weekly plot fits; plotting further back
  needs the worker rows cached when a window is plotted.
- A window launched before `window_launches` existed (Run 3: Nov 15, 16)
  is added to the State File by hand.
