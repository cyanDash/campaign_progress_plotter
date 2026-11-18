"""Tests for condor_fetcher.py -- turning condor_history / condor_q rows of
DAG worker nodes into plain dicts, in one call per schedd, with a cache for
finished DAGs. The subprocess calls are faked."""

import json
import subprocess

import condor_fetcher

# DAGManJobId, node, exit, memory, wall seconds, starts, request, lifetime
HISTORY = (
    "10\tSAM_START\t0\t73\t126.0\t1\t500\t43200.0\n"
    "10\tWORKER_0\t0\t8039\t35090.0\t1\t10240\t43200.0\n"
    "10\tWORKER_1\t88\t12208\t17181.0\t2\t10240\t43200.0\n"
    "10\tWORKER_2\t9\tundefined\t521.0\t1\tundefined\tundefined\n"
    "20\tWORKER_0\t0\t7000\t3600.0\t1\t16384\t43200.0\n"
)
# ClusterId, DAGManJobId, node, JobStatus, memory, request, lifetime
QUEUE_RUNNING = (
    "20\tundefined\tundefined\t2\tundefined\tundefined\tundefined\n"
    "21\t20\tSAM_END\t1\tundefined\t500\t43200.0\n"
    "22\t20\tWORKER_3\t2\t7945\t16384\t43200.0\n"
    "23\t20\tWORKER_4\t1\tundefined\t16384\t43200.0\n"
)
QUEUE_IDLE = "11\tundefined\tundefined\t4\tundefined\tundefined\tundefined\n"


def test_history_rows_keep_only_workers_with_hours_and_the_submitted_limits():
    workers = condor_fetcher.parse_history(HISTORY)

    assert [(w["dag"], w["node"]) for w in workers] == [("10", "WORKER_0"), ("10", "WORKER_1"), ("10", "WORKER_2"), ("20", "WORKER_0")]
    assert workers[0] == {"dag": "10", "node": "WORKER_0", "exit": 0, "mem_mb": 8039, "wall_h": 35090.0 / 3600,
                          "starts": 1, "request_mb": 10240, "limit_h": 12.0}
    assert workers[1]["exit"] == 88 and workers[1]["starts"] == 2


def test_history_row_without_attributes_has_none_for_them():
    row = condor_fetcher.parse_history(HISTORY)[2]

    assert row["mem_mb"] is None and row["request_mb"] is None and row["limit_h"] is None


def test_queue_gives_running_workers_and_the_dags_still_active():
    running, active = condor_fetcher.parse_queue(QUEUE_RUNNING)

    assert running == [{"dag": "20", "node": "WORKER_3", "exit": None, "mem_mb": 7945, "wall_h": None, "starts": None,
                        "request_mb": 16384, "limit_h": 12.0}]
    assert active == {"20"}


def test_a_completed_controller_in_the_queue_does_not_keep_its_dag_active():
    assert condor_fetcher.parse_queue(QUEUE_IDLE) == ([], set())


class Condor:
    """Stands in for subprocess.run: answers condor_history and condor_q by
    schedd and records every call."""

    def __init__(self, history, queue, fail_on=None):
        self.history, self.queue, self.fail_on, self.calls = history, queue, fail_on, []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        schedd = command[command.index("-name") + 1]
        if schedd == self.fail_on:
            raise subprocess.TimeoutExpired(command, 1)
        text = self.history if command[0].endswith("condor_history") else self.queue
        return subprocess.CompletedProcess(command, 0, stdout=text, stderr="")


def use(monkeypatch, condor):
    monkeypatch.setattr(condor_fetcher.subprocess, "run", condor)
    return condor


def test_every_dag_of_a_schedd_is_read_in_one_history_and_one_queue_call(monkeypatch):
    condor = use(monkeypatch, Condor(HISTORY, QUEUE_RUNNING))

    result = condor_fetcher.workers_many(["10@jobsub01.fnal.gov", "20@jobsub01.fnal.gov"])

    assert len(condor.calls) == 2
    assert "DAGManJobId==10" in " ".join(condor.calls[0]) and "DAGManJobId==20" in " ".join(condor.calls[0])
    assert [w["node"] for w in result["10@jobsub01.fnal.gov"]] == ["WORKER_0", "WORKER_1", "WORKER_2"]
    assert [w["node"] for w in result["20@jobsub01.fnal.gov"]] == ["WORKER_0", "WORKER_3"]
    assert all("dag" not in w for w in result["10@jobsub01.fnal.gov"])


def test_each_schedd_gets_its_own_calls(monkeypatch):
    condor = use(monkeypatch, Condor(HISTORY, ""))

    condor_fetcher.workers_many(["10@jobsub01.fnal.gov", "10@jobsub04.fnal.gov"])

    assert len(condor.calls) == 4
    assert {c[c.index("-name") + 1] for c in condor.calls} == {"jobsub01.fnal.gov", "jobsub04.fnal.gov"}


def test_finished_dags_are_cached_and_not_fetched_again(monkeypatch, tmp_path):
    cache = tmp_path / "cache" / "workers.json"
    condor = use(monkeypatch, Condor(HISTORY, QUEUE_RUNNING))

    first = condor_fetcher.workers_many(["10@jobsub01.fnal.gov", "20@jobsub01.fnal.gov"], str(cache))
    assert list(json.loads(cache.read_text())) == ["10@jobsub01.fnal.gov"]  # DAG 20 still has jobs in the queue

    condor.calls.clear()
    second = condor_fetcher.workers_many(["10@jobsub01.fnal.gov"], str(cache))

    assert condor.calls == [] and second["10@jobsub01.fnal.gov"] == first["10@jobsub01.fnal.gov"]


def test_unfinished_dag_is_fetched_again_next_time(monkeypatch, tmp_path):
    cache = tmp_path / "workers.json"
    condor = use(monkeypatch, Condor(HISTORY, QUEUE_RUNNING))
    condor_fetcher.workers_many(["20@jobsub01.fnal.gov"], str(cache))
    condor.calls.clear()

    condor_fetcher.workers_many(["20@jobsub01.fnal.gov"], str(cache))

    assert len(condor.calls) == 2


def test_dag_with_no_history_rows_is_not_cached(monkeypatch, tmp_path):
    cache = tmp_path / "workers.json"
    use(monkeypatch, Condor("", ""))

    assert condor_fetcher.workers_many(["30@jobsub01.fnal.gov"], str(cache))["30@jobsub01.fnal.gov"] == []
    assert not cache.exists()


def test_a_failing_schedd_gives_none_and_leaves_the_others(monkeypatch):
    use(monkeypatch, Condor(HISTORY, "", fail_on="jobsub04.fnal.gov"))

    result = condor_fetcher.workers_many(["10@jobsub01.fnal.gov", "10@jobsub04.fnal.gov"])

    assert result["10@jobsub04.fnal.gov"] is None and len(result["10@jobsub01.fnal.gov"]) == 3


def test_malformed_ids_give_none_without_calling_condor(monkeypatch):
    condor = use(monkeypatch, Condor(HISTORY, ""))

    assert condor_fetcher.workers_many(["not-a-job-id", None]) == {"not-a-job-id": None, None: None}
    assert condor.calls == []


def test_an_unreadable_cache_file_is_ignored(monkeypatch, tmp_path):
    cache = tmp_path / "workers.json"
    cache.write_text("{not json")
    use(monkeypatch, Condor(HISTORY, ""))

    assert len(condor_fetcher.workers_many(["10@jobsub01.fnal.gov"], str(cache))["10@jobsub01.fnal.gov"]) == 3


def test_calls_run_in_a_pool_of_at_most_four(monkeypatch):
    sizes = []

    class RecordingPool(condor_fetcher.ThreadPoolExecutor):
        def __init__(self, max_workers=None, **kwargs):
            sizes.append(max_workers)
            super().__init__(max_workers=max_workers, **kwargs)
    monkeypatch.setattr(condor_fetcher, "ThreadPoolExecutor", RecordingPool)
    use(monkeypatch, Condor(HISTORY, ""))

    condor_fetcher.workers_many([f"10@jobsub0{n}.fnal.gov" for n in range(1, 4)])

    assert sizes == [4] and condor_fetcher.MAX_PARALLEL_CALLS == 4


def test_every_schedd_is_answered_when_there_are_more_calls_than_the_pool(monkeypatch):
    condor = use(monkeypatch, Condor(HISTORY, ""))
    ids = [f"10@jobsub0{n}.fnal.gov" for n in range(1, 4)]

    result = condor_fetcher.workers_many(ids)

    assert len(condor.calls) == 6 and all(len(result[j]) == 3 for j in ids)
