#!/bin/bash
#
#SBATCH --job-name=ibm-qdmi-qktr
#SBATCH --account=qfw-test
#SBATCH --time=00:10:00
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#
# Run a GHZ circuit on the IBM Quantum System API simulator from
# docker-compose.ibmsim.yml (./do_ibmsim.sh up) over QDMI: MQT Core's QDMI
# driver opens MQSC's IBM device library (ibm-qdmi), which speaks IBM Quantum
# Platform's Qiskit Runtime REST API, against ibmsim-runtime, the overlay's
# Runtime front for the simulator. The QDMI counterpart of ibm-qrmi-qktr.sbatch,
# which reaches the same simulator through QRMI, with no account, no network
# and no cost. The actual work is in ibm-qdmi-qktr.py alongside this script.
#
# The device library allows plain HTTP only to loopback addresses and verifies
# every HTTPS peer, so ibmsim-runtime serves HTTPS with a certificate from a
# private CA it creates at each start and publishes to
# /mnt/ibmsim-tls/ca.crt; this script points CURL_CA_BUNDLE at it.
#
# Requires:
#   the ibmsim stack running on the cluster network (./do_ibmsim.sh status)
#   ibm-qdmi in the QFw venv (the image installs it; rebuild an image that
#   predates it with ./do_build.sh)
# Optional, each defaulting to what docker-compose.ibmsim.yml uses:
#   IBMSIM_RUNTIME_URL             the Runtime front (default: https://ibmsim-runtime:8291)
#   CURL_CA_BUNDLE                 CA the front's certificate is checked against
#                                  (default: /mnt/ibmsim-tls/ca.crt)
#   QFW_API_KEY                    IAM API key the simulator accepts
#                                  (default: qfw-ibmsim-apikey)
#   IBMSIM_SERVICE_CRN             (default: crn:v1:bluemix:public:quantum-computing:us-east:a/qfw-ibmsim:qfw-ibmsim::)
#   QFW_QPU_DEVICE_ALIAS           simulated backend: fake_lagos (7q, default),
#                                  fake_cairo (27q), fake_brisbane (127q),
#                                  fake_torino (133q)
#   IBMSIM_TEST_SHOTS              shots (default: 1024)
#
# No SLURM QPU reservation is needed -- this cluster's compute nodes declare
# no qpu GRES, and the test talks to the device library directly.
#
# Submit and print the output:
#
#   jobid=$(sbatch --parsable --wait /mnt/ibm-qdmi-qktr.sbatch); cat slurm-${jobid}.out
#
# or, polling faster than sbatch --wait does:
#
#   bash /mnt/sbatch_poll_wait.sh /mnt/ibm-qdmi-qktr.sbatch
#
# Pass options through the environment (sbatch exports it by default):
#
#   QFW_QPU_DEVICE_ALIAS=fake_brisbane bash /mnt/sbatch_poll_wait.sh /mnt/ibm-qdmi-qktr.sbatch
#
# rather than --export=ALL,VAR=..., which makes slurmd fetch the user's login
# environment with su, and that needs a clone() this container denies.

set -euo pipefail

SCRIPT_DIR=/mnt
QFW_BASE="${QFW_BASE:-/workspace/qfw-container-base}"
QFW_PREFIX="${QFW_PREFIX:-${QFW_BASE}/qfw-install}"
QFW_VENV="${QFW_VENV:-/opt/openqse/qfw-venv}"
RUNTIME_URL="${IBMSIM_RUNTIME_URL:-https://ibmsim-runtime:8291}"
export IBMSIM_RUNTIME_URL="${RUNTIME_URL}"
export CURL_CA_BUNDLE="${CURL_CA_BUNDLE:-/mnt/ibmsim-tls/ca.crt}"

echo "[$(date)] ibm-qdmi-qktr on $(hostname)"

if [ ! -f "${QFW_PREFIX}/bin/qfw-activate" ]; then
    echo "No QFw install at ${QFW_PREFIX}. Run ./do_qfw_build.sh on the host first." >&2
    exit 1
fi
source "${QFW_PREFIX}/bin/qfw-activate" --venv "${QFW_VENV}"

# Fail fast with a clear message if the stack is down, rather than after the
# device library's retrying client gives up. /version on the Runtime front
# also reports whether it can reach the simulator behind it.
if [ ! -s "${CURL_CA_BUNDLE}" ]; then
    echo "No CA certificate at ${CURL_CA_BUNDLE}; ibmsim-runtime publishes it when it starts. Run ./do_ibmsim.sh up on the host first." >&2
    exit 1
fi
if ! curl -fsS --max-time 5 --cacert "${CURL_CA_BUNDLE}" "${RUNTIME_URL%/}/version" >/dev/null; then
    echo "No Runtime front for the IBM simulator at ${RUNTIME_URL}. Run ./do_ibmsim.sh up on the host first." >&2
    exit 1
fi
if ! python -c 'import ibm.qdmi' 2>/dev/null; then
    echo "ibm-qdmi is not installed in ${QFW_VENV}; see the header of this script." >&2
    exit 1
fi

# Unbuffered: stdout is fully buffered once redirected to a file, so without
# this, prints never reach slurm-<jobid>.out until the process exits.
python -u "${SCRIPT_DIR}/ibm-qdmi-qktr.py"

echo "[$(date)] ibm-qdmi-qktr done on $(hostname)"
