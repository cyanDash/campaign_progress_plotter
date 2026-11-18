"""condor_fetcher -- the one seam this project uses to read the worker jobs of
poms_auto_submit Submissions from condor.

`workers_many(jobsub_job_ids, cache_path)` gives, per Submission, one dict per
worker node of its DAG: finished ones from condor_history, still-running ones
from condor_q. All DAGs on one schedd go in one condor_history and one
condor_q call, because condor_history scans the schedd's whole history and
that scan is nearly all of the time; up to MAX_PARALLEL_CALLS calls run at once. A DAG with nothing left in the queue is
finished, so its rows are kept in the cache file and never fetched again.
Tests substitute a fake with the same interface. Needs a bearer token (see
setup.sh); a Submission condor cannot read gets None.
"""

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

# System binaries, not the jobsub_lite wrappers: cron's PATH is /usr/bin:/bin.
CONDOR_HISTORY = "/usr/bin/condor_history"
CONDOR_Q = "/usr/bin/condor_q"
TIMEOUT_SECONDS = 300
# condor_history and condor_q calls running at once.
MAX_PARALLEL_CALLS = 4
RUNNING = "2"
# JobStatus values of a job that may still change: idle, running, held,
# transferring output, suspended.
ACTIVE = {"1", "2", "5", "6", "7"}
HISTORY_ATTRIBUTES = ["DAGManJobId", "DAGNodeName", "ExitCode", "MemoryUsage", "RemoteWallClockTime", "NumJobStarts",
                      "orig_RequestMemory", "orig_JOB_EXPECTED_MAX_LIFETIME"]
QUEUE_ATTRIBUTES = ["ClusterId", "DAGManJobId", "DAGNodeName", "JobStatus", "MemoryUsage",
                    "orig_RequestMemory", "orig_JOB_EXPECTED_MAX_LIFETIME"]


def _number(text, cast):
    try:
        return cast(text)
    except ValueError:
        return None


def _hours(seconds):
    return None if seconds is None else seconds / 3600


def _fields(line, count):
    return (line.split("\t") + [""] * count)[:count]


def parse_history(text):
    """Worker rows of `-af:t` over HISTORY_ATTRIBUTES, each with `dag`, the
    cluster of its DAG. An attribute condor does not have is None. request_mb
    and limit_h are what the job was submitted with: a memory hold raises
    RequestMemory afterwards, orig_RequestMemory keeps the first value."""
    workers = []
    for line in text.splitlines():
        dag, node, exit_code, mem, wall, starts, request, lifetime = _fields(line, 8)
        if "WORKER" not in node:
            continue
        workers.append({
            "dag": dag, "node": node, "exit": _number(exit_code, int), "mem_mb": _number(mem, int),
            "wall_h": _hours(_number(wall, float)), "starts": _number(starts, int),
            "request_mb": _number(request, int), "limit_h": _hours(_number(lifetime, float)),
        })
    return workers


def parse_queue(text):
    """(running workers, active DAGs) of `-af:t` over QUEUE_ATTRIBUTES for the
    DAG controllers and their nodes. Running workers have no exit code and no
    wall time yet. A DAG is active while its controller or any of its worker
    nodes is idle, running, held or suspended; `dag` is its cluster."""
    running, active = [], set()
    for line in text.splitlines():
        cluster, dag, node, status, mem, request, lifetime = _fields(line, 7)
        if status not in ACTIVE:
            continue
        if "WORKER" in node:
            active.add(dag)
            if status == RUNNING and _number(mem, int) is not None:
                running.append({
                    "dag": dag, "node": node, "exit": None, "mem_mb": int(mem), "wall_h": None, "starts": None,
                    "request_mb": _number(request, int), "limit_h": _hours(_number(lifetime, float)),
                })
        elif not node or node == "undefined":
            active.add(dag if dag.isdigit() else cluster)
        else:
            active.add(dag)
    return running, active


def _run(binary, schedd, constraint, attributes):
    command = [binary, "-name", schedd, "-constraint", constraint, "-af:t", *attributes]
    result = subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=True)
    return result.stdout


def _without_dag(worker):
    return {k: v for k, v in worker.items() if k != "dag"}


def _load_cache(path):
    try:
        with open(path) as f:
            cache = json.load(f)
    except (TypeError, OSError, json.JSONDecodeError):
        return {}
    return cache if isinstance(cache, dict) else {}


def _save_cache(path, cache):
    tmp = f"{path}.tmp"
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(tmp, "w") as f:
        json.dump(cache, f)
    os.replace(tmp, path)


def workers_many(jobsub_job_ids, cache_path=None):
    """{jobsub_job_id: worker dicts, or None} for DAG ids `<cluster>@<schedd>`.
    None for a malformed id or a schedd condor fails on. With `cache_path`, a
    finished DAG's rows are read from and written to that JSON file."""
    cache = _load_cache(cache_path) if cache_path else {}
    result, pending, fetched = {}, {}, False
    for jid in dict.fromkeys(jobsub_job_ids):
        cluster, _, schedd = (jid or "").partition("@")
        if jid in cache:
            result[jid] = cache[jid]
        elif cluster.isdigit() and schedd:
            pending.setdefault(schedd, []).append((jid, cluster))
        else:
            result[jid] = None
    calls = {}
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_CALLS) as pool:
        for schedd, items in pending.items():
            clusters = [cluster for _, cluster in items]
            calls[schedd] = (
                pool.submit(_run, CONDOR_HISTORY, schedd, " || ".join(f"DAGManJobId=={c}" for c in clusters),
                            HISTORY_ATTRIBUTES),
                pool.submit(_run, CONDOR_Q, schedd, " || ".join(f"DAGManJobId=={c} || ClusterId=={c}" for c in clusters),
                            QUEUE_ATTRIBUTES),
            )
    for schedd, items in pending.items():
        try:
            history, queue = (call.result() for call in calls[schedd])
        except (subprocess.SubprocessError, OSError) as e:
            print(f"Could not read condor on {schedd}: {e}")
            result.update({jid: None for jid, _ in items})
            continue
        finished_rows, (running_rows, active) = parse_history(history), parse_queue(queue)
        for jid, cluster in items:
            finished = [_without_dag(w) for w in finished_rows if w["dag"] == cluster]
            result[jid] = finished + [_without_dag(w) for w in running_rows if w["dag"] == cluster]
            if finished and cluster not in active:
                cache[jid], fetched = finished, True
    if cache_path and fetched:
        _save_cache(cache_path, cache)
    return result
