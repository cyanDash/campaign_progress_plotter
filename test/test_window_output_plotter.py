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


def test_daily_asks_condor_for_the_slice_and_the_recovery_of_the_window(tmp_path):
    condor = FakeCondor({"10@jobsub01.fnal.gov": [worker(0)], "20@jobsub01.fnal.gov": [worker(88, mem=14000, wall=12.1)]})

    out = wop.main(["daily", "2026-11-16"], sam=FakeSam(), output_directory=tmp_path, condor=condor,
                   state_file=state_with_nov15(tmp_path), cache_path=tmp_path / "c.json")

    assert condor.asked == ["10@jobsub01.fnal.gov", "20@jobsub01.fnal.gov"]
    assert (tmp_path / "sbnd_data_run3_keepup_daily.pdf").stat().st_size > 0 and out.endswith("daily.pdf")


def test_plot_still_written_when_condor_cannot_be_read(tmp_path, capsys):
    condor = FakeCondor()  # every workers() call answers None

    wop.main(["daily", "2026-11-16"], sam=FakeSam(), output_directory=tmp_path, condor=condor,
             state_file=state_with_nov15(tmp_path), cache_path=tmp_path / "c.json")

    assert (tmp_path / "sbnd_data_run3_keepup_daily.pdf").stat().st_size > 0
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
