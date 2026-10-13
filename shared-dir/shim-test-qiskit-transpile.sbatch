#!/bin/bash
#
#SBATCH --job-name=shim-test-qiskit-transpile
#SBATCH --account=qfw-test
#SBATCH --time=00:15:00
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#
# Run a GHZ circuit through QFw's QRMI/QDMI shim (services/svc_lib_qpm),
# used directly as a Python module -- no QPM service, no DEFw RPC. Targets
# IQM Resonance's free `garnet:mock` backend by default, the same target
# mqt-iqm.sbatch uses -- no tunnel, no real QPU time, just a Resonance API
# token. Companion to shim-test.sbatch, which transpiles with mqt-cc instead
# of Qiskit's own transpile(). The actual work is in
# shim-test-qiskit-transpile.py alongside this script.
#
# Requires:
#   QFW_API_KEY           your IQM Resonance API token
# Optional:
#   SHIM_TEST_LIB          qrmi or qdmi -- force this library's execution path
#                         (default: let the descriptor/execution-owner decide,
#                         normally qrmi)
#   QFW_QC_URL             IQM endpoint (default: https://resonance.iqm.tech/)
#   QFW_QPU_DEVICE_ALIAS   IQM quantum-computer alias (default: "garnet:mock")
#   SHIM_TEST_SHOTS        shots (default: 100 -- keep first runs small)
#   SHIM_TEST_TIMEOUT      run_circuit poll timeout, seconds (default: 600 --
#                         the mock backend can queue well past the 300s the
#                         drivers default to; keep this below --time above)
#
# No SLURM QPU reservation is needed -- this cluster's compute nodes declare
# no qpu GRES, and the shim talks to QRMI/QDMI directly as a Python module.
#
# Submit and print the output once per library:
#
#   jobid=$(sbatch --parsable --wait --export=ALL,QFW_API_KEY,SHIM_TEST_LIB=qdmi /mnt/shim-test-qiskit-transpile.sbatch); cat slurm-${jobid}.out
#   jobid=$(sbatch --parsable --wait --export=ALL,QFW_API_KEY,SHIM_TEST_LIB=qrmi /mnt/shim-test-qiskit-transpile.sbatch); cat slurm-${jobid}.out

set -euo pipefail

SCRIPT_DIR=/mnt
QFW_BASE="${QFW_BASE:-/workspace/qfw-container-base}"
QFW_PREFIX="${QFW_PREFIX:-${QFW_BASE}/qfw-install}"
QFW_VENV="${QFW_VENV:-${QFW_BASE}/qfw-venv}"

: "${QFW_API_KEY:?set QFW_API_KEY to your IQM Resonance API token}"

echo "[$(date)] shim-test-qiskit-transpile on $(hostname)"

if [ ! -f "${QFW_PREFIX}/bin/qfw-activate" ]; then
    echo "No QFw install at ${QFW_PREFIX}. Run ./do_qfw_build.sh on the host first." >&2
    exit 1
fi
source "${QFW_PREFIX}/bin/qfw-activate" --venv "${QFW_VENV}"

# Unbuffered: stdout is fully buffered once redirected to a file, so without
# this, prints never reach slurm-<jobid>.out until the process exits.
python -u "${SCRIPT_DIR}/shim-test-qiskit-transpile.py"

echo "[$(date)] shim-test-qiskit-transpile done on $(hostname)"
