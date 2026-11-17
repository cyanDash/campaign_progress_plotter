"""Tests for window_jobs.py -- which Submissions ran each plotted window, read
from poms_auto_submit's State File."""

import json
from datetime import datetime, timezone

from window_jobs import window_submissions

NOV15 = (datetime(2026, 11, 15, 6, tzinfo=timezone.utc), datetime(2026, 11, 15, 9, tzinfo=timezone.utc))
NOV16 = (datetime(2026, 11, 16, 6, tzinfo=timezone.utc), datetime(2026, 11, 16, 9, tzinfo=timezone.utc))
E15, E16 = int(NOV15[0].timestamp()), int(NOV16[0].timestamp())


def write_state(tmp_path, **sections):
    path = tmp_path / "state.json"
    path.write_text(json.dumps(sections))
    return path


SUBMISSIONS = {
    "1": {"jobsub_job_id": "10@jobsub01.fnal.gov", "subgroup": "pro"},
    "2": {"jobsub_job_id": "20@jobsub01.fnal.gov", "subgroup": "pro"},
    "3": {"jobsub_job_id": "30@jobsub04.fnal.gov", "subgroup": "pro"},
}


def test_slice_and_recovery_of_a_window_are_found(tmp_path):
    state = write_state(
        tmp_path, submissions=SUBMISSIONS,
        window_launches={str(E15): {"submission_id": "1"}},
        window_recovery={f"run3_raw_data_ongoing_abc_time_{E15}__{E15 + 10800}": {
            "recovery_dataset": "x", "submission_id": "2"}},
    )

    assert window_submissions(state, [NOV15]) == {E15: [
        {"kind": "slice", "submission_id": "1", "jobsub_job_id": "10@jobsub01.fnal.gov"},
        {"kind": "recovery", "submission_id": "2", "jobsub_job_id": "20@jobsub01.fnal.gov"},
    ]}


def test_only_the_plotted_windows_are_returned(tmp_path):
    state = write_state(
        tmp_path, submissions=SUBMISSIONS,
        window_launches={str(E15): {"submission_id": "1"}, str(E16): {"submission_id": "3"}},
    )

    assert list(window_submissions(state, [NOV16])) == [E16]


def test_window_with_no_recovery_needed_has_only_its_slice(tmp_path):
    state = write_state(
        tmp_path, submissions=SUBMISSIONS,
        window_launches={str(E15): {"submission_id": "1"}},
        window_recovery={f"run3_raw_data_ongoing_abc_time_{E15}__{E15 + 10800}": {"recovery_dataset": None}},
    )

    assert [s["kind"] for s in window_submissions(state, [NOV15])[E15]] == ["slice"]


def test_submission_missing_from_the_cache_has_no_jobsub_id(tmp_path):
    state = write_state(tmp_path, window_launches={str(E15): {"submission_id": "9"}})

    assert window_submissions(state, [NOV15])[E15][0]["jobsub_job_id"] is None


def test_missing_or_unreadable_state_gives_no_submissions(tmp_path):
    assert window_submissions(tmp_path / "nope.json", [NOV15]) == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert window_submissions(bad, [NOV15]) == {}


def test_state_without_the_window_sections_gives_no_submissions(tmp_path):
    assert window_submissions(write_state(tmp_path, last_split=3), [NOV15]) == {}
