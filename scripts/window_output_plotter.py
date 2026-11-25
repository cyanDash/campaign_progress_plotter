"""Grouped-bar plot of input vs output file counts per split window, for a
campaign run with poms_auto_submit's [split] window. Run after `source setup.sh`.

    window_output_plotter.py daily   [YYYY-MM-DD]   yesterday's window
    window_output_plotter.py weekly  [YYYY-MM-DD]   the last 7 windows

The optional date replaces today (Central) as the run date. Add --debug to also
plot worker exit status, memory and wall time from condor, written to
sbnd_data_run3_keepup_<mode>_debug.pdf instead.

Every run also appends to logs/window_output_plotter.log (git-ignored).
"""

import logging
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import condor_fetcher
import samweb_fetcher
from chart_renderer import render_window_chart, render_window_report
from split_windows import recent_window_bounds, collect_window_counts, CENTRAL
from window_jobs import window_submissions

#####################################################################
# Must match the campaign's ini ([split] first_start/step/window).
first_start = "2026-11-15 00:00"  # Central
step = timedelta(days=1)
window = timedelta(hours=3)
input_dataset = "run3_raw_data_ongoing"
campaign = "Auto_POMS_SBND2026A_Gen2_Run3_BeamLight"
version = "v10_14_02_08"
tiers = ["reco1", "larcvreco1", "histreco2", "flatcaf", "caf"]

output_directory = "/exp/sbnd/app/users/sbndpro/mcp/SBND2026A/srcs/sbnutil/keepups/sbnd/data_run3/plots"
# The ini name of the poms_auto_submit run; its State File names each window's
# slice and recovery Submissions.
state_name = "state_sbnd_beamlight_run3.json"
#####################################################################


def default_state_file():
    """poms_auto_submit's State File: under $POMS_AUTO_SUBMIT_DIR (setup.sh
    sets it), else the checkout beside this one."""
    root = os.environ.get("POMS_AUTO_SUBMIT_DIR") or Path(__file__).resolve().parent.parent.parent / "poms_auto_submit"
    return Path(root) / "logs" / campaign / state_name


def default_cache_path():
    """Where finished DAGs' worker rows are kept between runs (git-ignored)."""
    return Path(__file__).resolve().parent.parent / "cache" / "condor_workers.json"


def default_log_path():
    """The log every run appends to (git-ignored)."""
    return Path(__file__).resolve().parent.parent / "logs" / "window_output_plotter.log"


log = logging.getLogger("window_output_plotter")


def collect_workers(condor, state_file, bounds, cache_path=None):
    """Every worker of the slice and recovery Submissions of the windows in
    `bounds`, from condor in one batch, each tagged with its Submission's
    `kind` and `submission_id`. A Submission condor cannot read is skipped."""
    submissions = [s for found in window_submissions(state_file, bounds).values() for s in found]
    known = [s for s in submissions if s["jobsub_job_id"]]
    for s in submissions:
        if not s["jobsub_job_id"]:
            log.warning(f"No jobsub id for {s['kind']} Submission {s['submission_id']}; leaving it out.")
    by_job = condor.workers_many([s["jobsub_job_id"] for s in known], cache_path) if known else {}
    workers = []
    for s in known:
        found = by_job.get(s["jobsub_job_id"])
        if found is None:
            log.warning(f"No condor data for {s['kind']} Submission {s['submission_id']}; leaving it out.")
            continue
        workers.extend({**w, "kind": s["kind"], "submission_id": s["submission_id"]} for w in found)
    return workers


def main(argv, sam=samweb_fetcher, output_directory=output_directory, condor=condor_fetcher, state_file=None,
         cache_path=None, log_file=None):
    """Run `_plot` with its messages sent to stdout and appended, timestamped,
    to `log_file` (default `default_log_path()`). A failed run logs why, with
    the traceback for a crash, and still raises."""
    path = Path(log_file or default_log_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    handlers = [logging.FileHandler(path), logging.StreamHandler(sys.stdout)]
    handlers[0].setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    handlers[1].setFormatter(logging.Formatter("%(message)s"))
    for h in handlers:
        log.addHandler(h)
    log.setLevel(logging.INFO)
    started = time.monotonic()
    try:
        log.info("===== plot run start =====")
        out = _plot(argv, sam, output_directory, condor, state_file, cache_path)
        log.info(f"===== plot run end ===== elapsed {time.monotonic() - started:.1f}s")
        return out
    except SystemExit as e:
        log.error(f"run failed: {e}")
        raise
    except Exception:
        log.exception("run failed")
        raise
    finally:
        for h in handlers:
            log.removeHandler(h)
            h.close()


def _plot(argv, sam, output_directory, condor, state_file, cache_path):
    """Plot the window(s) chosen by `argv` ([mode, optional date, optional
    --debug]) and return the PDF path. `sam` is any object with `count(query)`,
    `condor` one with `workers_many(jobsub_job_ids, cache_path)`. Without
    --debug condor is not asked and the plot is the bar chart alone; with it,
    the worker panels are added (still the bar chart alone if no worker data)."""
    debug = "--debug" in argv
    argv = [a for a in argv if a != "--debug"]
    mode = argv[0] if argv else "daily"
    count = {"daily": 1, "weekly": 7}[mode]
    today = date.fromisoformat(argv[1]) if len(argv) > 1 else datetime.now(CENTRAL).date()
    log.info(f"mode={mode} date={today} debug={debug}")

    bounds = recent_window_bounds(today, first_start, step, window, count)
    if not bounds:
        sys.exit(f"No window has started before {today}; nothing to plot.")
    for start, end in bounds:
        log.info(f"window {start.astimezone(CENTRAL):%Y-%m-%d %H:%M} to {end.astimezone(CENTRAL):%H:%M} CST")
    definitions = [f"data_SBND2026A_{campaign}_{version}_{t}_sbnd" for t in tiers]

    rows = collect_window_counts(sam, input_dataset, definitions, bounds)
    series = {"input": rows["input"], **{t: rows[d] for t, d in zip(tiers, definitions)}}

    labels = [s.astimezone(CENTRAL).strftime("%a %d %b") for s, _ in bounds]
    hours = int(window.total_seconds() // 3600)
    start_local = bounds[0][0].astimezone(CENTRAL).strftime("%H:%M")
    end_local = bounds[0][1].astimezone(CENTRAL).strftime("%H:%M")
    filename = f"{output_directory}/sbnd_data_run3_keepup_{mode}{'_debug' if debug else ''}.pdf"
    title = f"Input vs output files per split window ({start_local}-{end_local} Central, {hours}h window, step {step.days}d)"
    workers = collect_workers(condor, state_file or default_state_file(), bounds, cache_path or default_cache_path()) if debug else []
    if workers:
        render_window_report(labels, series, workers, title=title, filename=filename)
    else:
        render_window_chart(labels, series, title=title, filename=filename)
    log.info(f"counts: {series}")
    log.info(f"plot written: {filename}")
    return filename


if __name__ == "__main__":
    main(sys.argv[1:])
