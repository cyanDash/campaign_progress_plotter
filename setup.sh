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

# poms_auto_submit's checkout: its State File names each window's slice and
# recovery Submissions. Override by exporting POMS_AUTO_SUBMIT_DIR first.
POMS_AUTO_SUBMIT_DIR="${POMS_AUTO_SUBMIT_DIR:-${_plotter_dir}/../poms_auto_submit}"
if [[ -d "${POMS_AUTO_SUBMIT_DIR}" ]]; then
    export POMS_AUTO_SUBMIT_DIR="$(cd "${POMS_AUTO_SUBMIT_DIR}" && pwd)"
else
    echo "POMS_AUTO_SUBMIT_DIR=${POMS_AUTO_SUBMIT_DIR} does not exist; plots will be SAM-only" >&2
    unset POMS_AUTO_SUBMIT_DIR
fi

# condor_history/condor_q need a bearer token for the worker-resource plots.
# Without one the plots are SAM-only.
export HTGETTOKENOPTS="--credkey=sbndpro/managedtokens/fifeutilgpvm01.fnal.gov -r production -a htvaultprod.fnal.gov -i sbnd"
export BEARER_TOKEN_FILE="/tmp/bt_u$(id -u)_campaign_progress_plotter"
htgettoken || echo "no condor token; plots will be SAM-only" >&2
