#!/bin/bash
#
#SBATCH --job-name=ibmsim-test
#SBATCH --account=qfw-test
#SBATCH --time=00:10:00
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#
# Run a GHZ circuit through QFw's QRMI/QDMI shim (services/svc_lib_qpm),
# used directly as a Python module -- no QPM service, no DEFw RPC -- against
# the IBM Quantum System API simulator from docker-compose.ibmsim.yml
# (./do_ibmsim.sh up). QRMI's IBMQuantumSystem resource is the client,
# unchanged from what reaches a real IBM system, so this is the IBM
# counterpart of shim-test.sbatch with no account, no network and no cost.
# The actual work is in ibmsim-test.py alongside this script.
#
# Requires:
#   the ibmsim stack running on the cluster network (./do_ibmsim.sh status)
# Optional, each defaulting to what docker-compose.ibmsim.yml uses:
#   QFW_QC_URL                     simulator endpoint (default: http://ibmsim:8290)
#   QFW_API_KEY                    IAM API key the simulator accepts
#                                  (default: qfw-ibmsim-apikey)
#   IBMSIM_SERVICE_CRN             (default: crn:v1:local:qfw-ibmsim)
#   IBMSIM_S3_ENDPOINT             (default: http://ibmsim-s3:9000)
#   IBMSIM_S3_BUCKET               (default: qfw-ibmsim)
#   IBMSIM_S3_REGION               (default: us-east-1)
#   QFW_IBM_AWS_ACCESS_KEY_ID      (default: qfw-ibmsim-access)
#   QFW_IBM_AWS_SECRET_ACCESS_KEY  (default: qfw-ibmsim-secret)
#   QFW_QPU_DEVICE_ALIAS           simulated backend: fake_lagos (7q, default),
#                                  fake_cairo (27q), fake_brisbane (127q),
#                                  fake_torino (133q)
#   IBMSIM_TEST_SHOTS              shots (default: 1024)
#   IBMSIM_TEST_TIMEOUT            job timeout, seconds (default: 300; keep
#                                  it below --time above)
#
# No SLURM QPU reservation is needed -- this cluster's compute nodes declare
# no qpu GRES, and the shim talks to QRMI directly as a Python module.
#
# Submit and print the output:
#
#   jobid=$(sbatch --parsable --wait /mnt/ibmsim-test.sbatch); cat slurm-${jobid}.out
#
# or, polling faster than sbatch --wait does:
#
#   bash /mnt/sbatch_poll_wait.sh /mnt/ibmsim-test.sbatch
#
# Pass options through the environment (sbatch exports it by default):
#
#   QFW_QPU_DEVICE_ALIAS=fake_brisbane bash /mnt/sbatch_poll_wait.sh /mnt/ibmsim-test.sbatch
#
# rather than --export=ALL,VAR=..., which makes slurmd fetch the user's login
# environment with su, and that needs a clone() this container denies.

set -euo pipefail

SCRIPT_DIR=/mnt
QFW_BASE="${QFW_BASE:-/workspace/qfw-container-base}"
QFW_PREFIX="${QFW_PREFIX:-${QFW_BASE}/qfw-install}"
QFW_VENV="${QFW_VENV:-/opt/openqse/qfw-venv}"

echo "[$(date)] ibmsim-test on $(hostname)"

if [ ! -f "${QFW_PREFIX}/bin/qfw-activate" ]; then
    echo "No QFw install at ${QFW_PREFIX}. Run ./do_qfw_build.sh on the host first." >&2
    exit 1
fi
source "${QFW_PREFIX}/bin/qfw-activate" --venv "${QFW_VENV}"

# Fail fast with a clear message if the stack is down, rather than after
# QRMI's retrying client gives up.
IBMSIM_URL="${QFW_QC_URL:-http://ibmsim:8290}"
if ! curl -fsS --max-time 5 "${IBMSIM_URL%/}/version" >/dev/null; then
    echo "No IBM Quantum System API simulator at ${IBMSIM_URL}. Run ./do_ibmsim.sh up on the host first." >&2
    exit 1
fi

# Unbuffered: stdout is fully buffered once redirected to a file, so without
# this, prints never reach slurm-<jobid>.out until the process exits.
python -u "${SCRIPT_DIR}/ibmsim-test.py"

echo "[$(date)] ibmsim-test done on $(hostname)"
