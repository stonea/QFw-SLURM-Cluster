#!/bin/bash
#
#SBATCH --job-name=ibm-shim-qktr
#SBATCH --account=qfw-test
#SBATCH --time=00:10:00
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#
# Run a GHZ circuit through QFw's QRMI/QDMI shim (services/svc_lib_qpm),
# used directly as a Python module -- no QPM service, no DEFw RPC. Targets
# the IBM Quantum System API simulator from docker-compose.ibmsim.yml
# (./do_ibmsim.sh up), the same target ibm-qrmi-qktr.sbatch and
# ibm-qdmi-qktr.sbatch use -- no IBM account, no network, no cost. The IBM
# counterpart of iqm-shim-qktr.sbatch: it transpiles with Qiskit's own
# transpile(). The actual work is in ibm-shim-qktr.py alongside this script.
#
# QRMI's IBMQuantumSystem reaches the simulator directly; QDMI's IBM device
# library reaches it through ibmsim-runtime, the overlay's Qiskit Runtime
# front, which serves HTTPS with a certificate from a private CA it publishes
# at /mnt/ibmsim-tls/ca.crt. This script points CURL_CA_BUNDLE at it.
#
# Requires:
#   the ibmsim stack running on the cluster network (./do_ibmsim.sh status)
#   a QFw install with the IBM QDMI profile, and ibm-qdmi in its venv. The
#   image's venv has ibm-qdmi, but until the profile reaches QFw's main
#   branch the image's /opt/openqse/qfw install, which the login
#   environment's QFW_PREFIX points at, lacks the profile, so this script
#   falls back to the developer install under QFW_BASE (./do_qfw_build.sh)
#   on the image's venv when that has it.
# Optional, each defaulting to what docker-compose.ibmsim.yml uses:
#   SHIM_TEST_LIB                  qrmi or qdmi -- force this library's execution
#                                  path (default: let the descriptor/execution-
#                                  owner decide, normally qrmi)
#   QFW_QC_URL                     simulator endpoint (default: http://ibmsim:8290)
#   IBMSIM_RUNTIME_URL             the Runtime front (default: https://ibmsim-runtime:8291)
#   CURL_CA_BUNDLE                 (default: /mnt/ibmsim-tls/ca.crt)
#   IBMSIM_API_KEY                 (default: qfw-ibmsim-apikey). An exported
#                                  QFW_API_KEY is ignored; see below.
#   IBMSIM_SERVICE_CRN             (default: crn:v1:bluemix:public:quantum-computing:us-east:a/qfw-ibmsim:qfw-ibmsim::)
#   IBMSIM_S3_ENDPOINT             (default: http://ibmsim-s3:9000)
#   IBMSIM_S3_BUCKET               (default: qfw-ibmsim)
#   IBMSIM_S3_REGION               (default: us-east-1)
#   QFW_IBM_AWS_ACCESS_KEY_ID      (default: qfw-ibmsim-access)
#   QFW_IBM_AWS_SECRET_ACCESS_KEY  (default: qfw-ibmsim-secret)
#   QFW_QPU_DEVICE_ALIAS           simulated backend: fake_lagos (7q, default),
#                                  fake_cairo (27q), fake_brisbane (127q),
#                                  fake_torino (133q)
#   SHIM_TEST_SHOTS                shots (default: 1024)
#   SHIM_TEST_TIMEOUT              run_circuit poll timeout, seconds (default:
#                                  300; keep it below --time above)
#
# No SLURM QPU reservation is needed -- this cluster's compute nodes declare
# no qpu GRES, and the shim talks to QRMI/QDMI directly as a Python module.
#
# Submit and print the output once per library:
#
#   SHIM_TEST_LIB=qrmi bash /mnt/sbatch_poll_wait.sh /mnt/ibm-shim-qktr.sbatch
#   SHIM_TEST_LIB=qdmi bash /mnt/sbatch_poll_wait.sh /mnt/ibm-shim-qktr.sbatch
#
# Pass options through the environment (sbatch exports it by default) rather
# than --export=ALL,VAR=..., which makes slurmd fetch the user's login
# environment with su, and that needs a clone() this container denies.

set -euo pipefail

SCRIPT_DIR=/mnt
QFW_BASE="${QFW_BASE:-/workspace/qfw-container-base}"
QFW_PREFIX="${QFW_PREFIX:-${QFW_BASE}/qfw-install}"
QFW_VENV="${QFW_VENV:-/opt/openqse/qfw-venv}"
IBMSIM_URL="${QFW_QC_URL:-http://ibmsim:8290}"
RUNTIME_URL="${IBMSIM_RUNTIME_URL:-https://ibmsim-runtime:8291}"
export CURL_CA_BUNDLE="${CURL_CA_BUNDLE:-/mnt/ibmsim-tls/ca.crt}"

# sbatch exports the submitting shell, where QFW_API_KEY is often the IQM
# Resonance token the iqm-* tests need. The simulator rejects it, so always
# hand the shim the simulator's key.
export QFW_API_KEY="${IBMSIM_API_KEY:-qfw-ibmsim-apikey}"

echo "[$(date)] ibm-shim-qktr on $(hostname)"

# Whether a QFw install has what this test needs: ibm-qdmi in its venv and
# QFw's IBM QDMI profile. qfw-activate follows the exported QFW_PREFIX, so
# each candidate is checked in a subshell with its own exports.
has_ibm_qdmi() {
    [ -f "$1/bin/qfw-activate" ] || return 1
    (
        export QFW_PREFIX="$1" QFW_VENV="$2"
        source "$1/bin/qfw-activate" --venv "$2" >/dev/null 2>&1
        python -c 'import ibm.qdmi, defw; from svc_lib_qpm.drivers.qdmi_profiles import IbmQdmiProfile' 2>/dev/null
    )
}

# The login environment points QFW_PREFIX at the image's install
# (/opt/openqse/qfw), which predates the IBM QDMI profile, so fall back to the
# developer install under QFW_BASE when that one has it.
if ! has_ibm_qdmi "${QFW_PREFIX}" "${QFW_VENV}"; then
    if has_ibm_qdmi "${QFW_BASE}/qfw-install" "${QFW_VENV}"; then
        echo "${QFW_PREFIX} lacks ibm-qdmi or QFw's IBM QDMI profile; using ${QFW_BASE}/qfw-install"
        QFW_PREFIX="${QFW_BASE}/qfw-install"
    else
        echo "Neither ${QFW_PREFIX} nor ${QFW_BASE}/qfw-install has ibm-qdmi and QFw's IBM QDMI profile." >&2
        echo "Run ./do_qfw_build.sh on the host first." >&2
        exit 1
    fi
fi
export QFW_PREFIX QFW_VENV
source "${QFW_PREFIX}/bin/qfw-activate" --venv "${QFW_VENV}"

# Fail fast with a clear message if the stack is down, rather than after the
# clients' retrying HTTP stacks give up.
if ! curl -fsS --max-time 5 "${IBMSIM_URL%/}/version" >/dev/null; then
    echo "No IBM Quantum System API simulator at ${IBMSIM_URL}. Run ./do_ibmsim.sh up on the host first." >&2
    exit 1
fi
if ! curl -fsS --max-time 5 --cacert "${CURL_CA_BUNDLE}" "${RUNTIME_URL%/}/version" >/dev/null; then
    echo "No Runtime front for the IBM simulator at ${RUNTIME_URL} (CA ${CURL_CA_BUNDLE}). Run ./do_ibmsim.sh up on the host first." >&2
    exit 1
fi

# Unbuffered: stdout is fully buffered once redirected to a file, so without
# this, prints never reach slurm-<jobid>.out until the process exits.
python -u "${SCRIPT_DIR}/ibm-shim-qktr.py"

echo "[$(date)] ibm-shim-qktr done on $(hostname)"
