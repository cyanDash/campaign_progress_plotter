"""Tests for window_output_plotter.py -- the cron entry point -- against a fake
SAM seam. Run with: pytest
"""

import json

import pytest

import window_output_plotter as wop
from datetime import datetime, timezone


class FakeSam:
    def __init__(self):
        self.queries = []

    def count(self, query):
        self.queries.append(query)
        return 10


class FakeCondor:
    def __init__(self, by_job=None):
        self.by_job = by_job or {}
        self.asked = []

    def workers_many(self, jobsub_job_ids, cache_path=None):
        self.asked.extend(jobsub_job_ids)
        return {j: self.by_job.get(j) for j in jobsub_job_ids}


NO_STATE = "no_such_state.json"
NOV15_EPOCH = int(datetime(2026, 11, 15, 6, tzinfo=timezone.utc).timestamp())


def state_with_nov15(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({
        "submissions": {"1": {"jobsub_job_id": "10@jobsub01.fnal.gov"}, "2": {"jobsub_job_id": "20@jobsub01.fnal.gov"}},
        "window_launches": {str(NOV15_EPOCH): {"submission_id": "1"}},
        "window_recovery": {f"run3_raw_data_ongoing_x_time_{NOV15_EPOCH}__{NOV15_EPOCH + 10800}": {"submission_id": "2"}},
    }))
    return path


def worker(exit_code, mem=8000, wall=3.0):
    return {"node": "WORKER_0", "exit": exit_code, "mem_mb": mem, "wall_h": wall, "starts": 1}


def test_daily_plots_yesterdays_window_to_the_keepup_filename(tmp_path):
    sam = FakeSam()
    out = wop.main(["daily", "2026-11-16"], sam=sam, output_directory=tmp_path, condor=FakeCondor(), state_file=tmp_path / NO_STATE, cache_path=tmp_path / "c.json")
    assert out == f"{tmp_path}/sbnd_data_run3_keepup_daily.pdf"
    assert (tmp_path / "sbnd_data_run3_keepup_daily.pdf").stat().st_size > 0
    # 2026-11-15 00:00-03:00 Central is 06:00-09:00 UTC; input + 5 tiers.
    assert len(sam.queries) == 6
    assert "create_date >= '2026-11-15T06:00:00' and create_date < '2026-11-15T09:00:00'" in sam.queries[0]


def test_weekly_names_the_weekly_file(tmp_path):
    out = wop.main(["weekly", "2026-11-22"], sam=FakeSam(), output_directory=tmp_path, condor=FakeCondor(), state_file=tmp_path / NO_STATE, cache_path=tmp_path / "c.json")
    assert out.endswith("sbnd_data_run3_keepup_weekly.pdf")
    assert (tmp_path / "sbnd_data_run3_keepup_weekly.pdf").exists()


def test_exits_before_the_first_window_has_started(tmp_path):
    with pytest.raises(SystemExit, match="nothing to plot"):
        wop.main(["daily", "2026-11-15"], sam=FakeSam(), output_directory=tmp_path, condor=FakeCondor(), state_file=tmp_path / NO_STATE, cache_path=tmp_path / "c.json")


def test_plain_run_never_asks_condor(tmp_path):
    condor = FakeCondor({"10@jobsub01.fnal.gov": [worker(0)]})

    out = wop.main(["daily", "2026-11-16"], sam=FakeSam(), output_directory=tmp_path, condor=condor,
                   state_file=state_with_nov15(tmp_path), cache_path=tmp_path / "c.json")

    assert condor.asked == [] and out.endswith("keepup_daily.pdf")


def test_debug_writes_the_separate_debug_file(tmp_path):
    condor = FakeCondor({"10@jobsub01.fnal.gov": [worker(0)], "20@jobsub01.fnal.gov": [worker(0)]})

    out = wop.main(["weekly", "2026-11-16", "--debug"], sam=FakeSam(), output_directory=tmp_path, condor=condor,
                   state_file=state_with_nov15(tmp_path), cache_path=tmp_path / "c.json")

    assert out.endswith("keepup_weekly_debug.pdf") and (tmp_path / "sbnd_data_run3_keepup_weekly_debug.pdf").exists()
    assert condor.asked


def test_daily_asks_condor_for_the_slice_and_the_recovery_of_the_window(tmp_path):
    condor = FakeCondor({"10@jobsub01.fnal.gov": [worker(0)], "20@jobsub01.fnal.gov": [worker(88, mem=14000, wall=12.1)]})

    out = wop.main(["daily", "2026-11-16", "--debug"], sam=FakeSam(), output_directory=tmp_path, condor=condor,
                   state_file=state_with_nov15(tmp_path), cache_path=tmp_path / "c.json")

    assert condor.asked == ["10@jobsub01.fnal.gov", "20@jobsub01.fnal.gov"]
    assert (tmp_path / "sbnd_data_run3_keepup_daily_debug.pdf").stat().st_size > 0 and out.endswith("daily_debug.pdf")


def test_plot_still_written_when_condor_cannot_be_read(tmp_path, capsys):
    condor = FakeCondor()  # every workers() call answers None

    wop.main(["daily", "2026-11-16", "--debug"], sam=FakeSam(), output_directory=tmp_path, condor=condor,
             state_file=state_with_nov15(tmp_path), cache_path=tmp_path / "c.json")

    assert (tmp_path / "sbnd_data_run3_keepup_daily_debug.pdf").stat().st_size > 0
    assert "No condor data for slice Submission 1" in capsys.readouterr().out


def test_default_state_file_follows_poms_auto_submit_dir(monkeypatch):
    monkeypatch.setenv("POMS_AUTO_SUBMIT_DIR", "/somewhere/poms_auto_submit")

    assert str(wop.default_state_file()) == (
        "/somewhere/poms_auto_submit/logs/Auto_POMS_SBND2026A_Gen2_Run3_BeamLight/state_sbnd_beamlight_run3.json")


def test_default_state_file_falls_back_to_the_checkout_beside_this_one(monkeypatch):
    monkeypatch.delenv("POMS_AUTO_SUBMIT_DIR", raising=False)

    assert wop.default_state_file().parts[-4:-2] == ("poms_auto_submit", "logs")


def test_collect_workers_tags_each_worker_with_its_submission(tmp_path):
    condor = FakeCondor({"10@jobsub01.fnal.gov": [worker(0)], "20@jobsub01.fnal.gov": [worker(88)]})
    bounds = [(datetime(2026, 11, 15, 6, tzinfo=timezone.utc), datetime(2026, 11, 15, 9, tzinfo=timezone.utc))]

    workers = wop.collect_workers(condor, state_with_nov15(tmp_path), bounds)

    assert [(w["kind"], w["submission_id"]) for w in workers] == [("slice", "1"), ("recovery", "2")]


def run_logged(tmp_path, argv, condor=None, state=None):
    log = tmp_path / "run.log"
    wop.main(argv, sam=FakeSam(), output_directory=tmp_path, condor=condor or FakeCondor(),
             state_file=state or tmp_path / NO_STATE, cache_path=tmp_path / "c.json", log_file=log)
    return log.read_text()


def test_log_records_the_run_start_to_end(tmp_path):
    text = run_logged(tmp_path, ["weekly", "2026-11-16", "--debug"],
                      condor=FakeCondor(), state=state_with_nov15(tmp_path))

    assert "===== plot run start =====" in text and "===== plot run end" in text
    assert "mode=weekly date=2026-11-16 debug=True" in text
    assert "window 2026-11-15 00:00 to 03:00 CST" in text
    assert "{'input': [10]" in text  # the counts, as printed to stdout
    assert f"{tmp_path}/sbnd_data_run3_keepup_weekly_debug.pdf" in text
    assert "elapsed" in text
    assert "No condor data for slice Submission 1" in text


def test_a_failing_run_logs_the_error_and_does_not_end_normally(tmp_path):
    log = tmp_path / "run.log"
    with pytest.raises(SystemExit, match="nothing to plot"):
        wop.main(["daily", "2026-11-15"], sam=FakeSam(), output_directory=tmp_path, condor=FakeCondor(),
                 state_file=tmp_path / NO_STATE, cache_path=tmp_path / "c.json", log_file=log)

    text = log.read_text()
    assert "===== plot run start =====" in text
    assert "run failed" in text and "nothing to plot" in text
    assert "===== plot run end" not in text


def test_a_crash_logs_its_traceback_and_still_raises(tmp_path):
    class BrokenSam:
        def count(self, query):
            raise RuntimeError("samweb down")

    log = tmp_path / "run.log"
    with pytest.raises(RuntimeError, match="samweb down"):
        wop.main(["daily", "2026-11-16"], sam=BrokenSam(), output_directory=tmp_path, condor=FakeCondor(),
                 state_file=tmp_path / NO_STATE, cache_path=tmp_path / "c.json", log_file=log)

    text = log.read_text()
    assert "run failed" in text and "Traceback" in text and "samweb down" in text


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_prints_usage_and_exits_without_plotting_or_logging(tmp_path, capsys, flag):
    sam, log = FakeSam(), tmp_path / "run.log"

    with pytest.raises(SystemExit) as stop:
        wop.main([flag], sam=sam, output_directory=tmp_path, condor=FakeCondor(), log_file=log)

    out = capsys.readouterr().out
    assert stop.value.code == 0
    assert all(w in out for w in ("daily", "weekly", "monthly", "--debug", "keepup_<mode>.pdf", "logs/window_output_plotter.log"))
    assert sam.queries == [] and not log.exists() and not list(tmp_path.glob("*.pdf"))


def test_monthly_plots_the_last_30_windows_with_only_input_and_flatcaf(tmp_path):
    sam = FakeSam()

    out = wop.main(["monthly", "2026-12-20"], sam=sam, output_directory=tmp_path, condor=FakeCondor(),
                   state_file=tmp_path / NO_STATE, cache_path=tmp_path / "c.json")

    assert out == f"{tmp_path}/sbnd_data_run3_keepup_monthly.pdf"
    assert (tmp_path / "sbnd_data_run3_keepup_monthly.pdf").stat().st_size > 0
    assert len(sam.queries) == 60  # 30 windows x (input + flatcaf)
    assert sum("flatcaf" in q for q in sam.queries) == 30
    assert not any(t in q for q in sam.queries for t in ("reco1", "histreco2", "_caf_sbnd"))
    # 2026-11-20 00:00 Central (CST) is 06:00 UTC: the oldest of the 30 days before Dec 20.
    assert "create_date >= '2026-11-20T06:00:00'" in sam.queries[0]


def test_monthly_early_in_the_campaign_plots_only_the_windows_that_exist(tmp_path):
    sam = FakeSam()

    wop.main(["monthly", "2026-11-25"], sam=sam, output_directory=tmp_path, condor=FakeCondor(),
             state_file=tmp_path / NO_STATE, cache_path=tmp_path / "c.json")

    assert len(sam.queries) == 20  # Nov 15 to Nov 24: 10 windows


def test_monthly_labels_are_month_over_day_but_weekly_keeps_the_weekday(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(wop, "render_window_chart", lambda labels, series, **kw: seen.setdefault(kw["filename"].split("keepup_")[1], labels))

    for mode in ("monthly", "weekly"):
        wop.main([mode, "2026-11-25"], sam=FakeSam(), output_directory=tmp_path, condor=FakeCondor(),
                 state_file=tmp_path / NO_STATE, cache_path=tmp_path / "c.json")

    assert seen["monthly.pdf"][0] == "Nov\n15" and seen["monthly.pdf"][-1] == "Nov\n24"
    assert seen["weekly.pdf"][0] == "Wed 18 Nov"


@pytest.mark.parametrize("argv, message", [
    (["monthly", "--dubug"], "unknown option '--dubug'"),
    (["monthly", "2026-13-45"], "not a YYYY-MM-DD date: '2026-13-45'"),
    (["yearly"], "unknown mode 'yearly'"),
])
def test_bad_arguments_exit_with_a_short_message_pointing_to_help(tmp_path, argv, message):
    sam = FakeSam()

    with pytest.raises(SystemExit) as stop:
        wop.main(argv, sam=sam, output_directory=tmp_path, condor=FakeCondor(), log_file=tmp_path / "run.log")

    assert message in str(stop.value) and "--help" in str(stop.value)
    assert sam.queries == [] and not list(tmp_path.glob("*.pdf"))
