"""samweb_fetcher -- the single seam this project uses to talk to SAM.

Consolidates the subprocess invocation, error handling, and samweb CLI output
parsing that used to be duplicated across three separate wrapper functions.
Production code calls these functions directly (they shell out to the real
`samweb` CLI); tests substitute a fake with the same interface.

Make sure your environment is set up and samweb-client is active before calling
any of these.
"""

import subprocess
from datetime import datetime


def file_count(dataset, before):
    """Return the number of files in `dataset` created before `before` (a date),
    or None if the samweb query fails."""
    command = f"samweb list-files 'defname:{dataset} and create_date < {before}' --summary"
    try:
        result = subprocess.check_output(command, shell=True, executable="/bin/bash", stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while fetching files from dataset {dataset}: {e.output}. \n Make sure your environment is set up and samweb-client is active.")
        return None
    return int(result.splitlines()[0].decode('utf-8').split('\t')[1])


def count(query):
    """Return the number of files matching the SAM dimension `query`, or None if
    the samweb query fails."""
    try:
        result = subprocess.check_output(
            ["samweb", "list-files", query, "--summary"], stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while counting files for query {query}: {e.output}. \n Make sure your environment is set up and samweb-client is active.")
        return None
    return int(result.splitlines()[0].decode('utf-8').split('\t')[1])


def creation_time(dataset):
    """Return the (UTC, timezone-aware) datetime `dataset`'s definition was
    created, or None if the samweb query fails."""
    command = f"samweb describe-definition {dataset} | grep 'Creation' | awk -F': ' '{{print $2}}'"
    try:
        result = subprocess.check_output(command, shell=True, executable="/bin/bash", stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while fetching creation time for dataset {dataset}: {e.output}. \n Make sure your environment is set up and samweb-client is active.")
        return None
    return datetime.fromisoformat(result.decode('utf-8').strip())


def exists(dataset):
    """Return True if `dataset`'s definition exists in SAM."""
    result = subprocess.run(
        f"samweb describe-definition {dataset}",
        shell=True, executable="/bin/bash",
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0
