#! /usr/bin/env bash
# Source this script (source setup.sh) before running scripts/*.py.
# Builds ./venv from requirements.txt on first use, then activates it.

_plotter_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -d "${_plotter_dir}/venv" ]]; then
    echo "creating venv at ${_plotter_dir}/venv"
    python3 -m venv "${_plotter_dir}/venv" \
        && "${_plotter_dir}/venv/bin/pip" install -q -r "${_plotter_dir}/requirements.txt" \
        || { echo "venv build failed; removing ${_plotter_dir}/venv" >&2; rm -rf "${_plotter_dir}/venv"; }
fi
source "${_plotter_dir}/venv/bin/activate"

source /cvmfs/fermilab.opensciencegrid.org/products/common/etc/setups.sh
setup sam_web_client
export SAM_EXPERIMENT=sbnd

# The shared home may not be writable (e.g. as sbndpro); give matplotlib a cache it can write.
export MPLCONFIGDIR="/tmp/matplotlib_${USER}"
mkdir -p "${MPLCONFIGDIR}"
