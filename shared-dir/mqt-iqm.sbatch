#!/bin/bash
#
#SBATCH --job-name=mqt-iqm
#SBATCH --time=00:30:00
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#
# Discover a live IQM quantum computer through MQT Core's QDMI driver, then
# run a GHZ circuit on it through IQM's Qiskit backend. As shipped it targets
# the `garnet:mock` device on IQM Resonance (https://resonance.iqm.tech/), a
# free mock backend that needs only a Resonance API token -- no QPU time.
# The actual work is in mqt-iqm.py alongside this script.
#
# This is the live-service counterpart to mqt-cc-smoke-test.sbatch: that one
# targets MQT Core's bundled, offline `mqt.sc.iqm.garnet` snapshot and runs on
# DDSIM; this one opens the real device via IQM's `iqm-qdmi` QDMI library.
#
# The path is QDMI end to end and does NOT go through QFw's QPM / QRMI
# reservation plane -- the `iqm-qdmi` device library talks to the IQM Server over
# HTTPS directly, exactly like the QDMI introspection leg of shim-smoke.sbatch.
# It therefore needs no `--gres=qpu` allocation, only the endpoint and a token.
#
# Requires:
#   QFW_API_KEY   your IQM Resonance API token
# Optional:
#   QFW_QC_URL            IQM endpoint (default: https://resonance.iqm.tech/)
#   QFW_QPU_DEVICE_ALIAS  IQM quantum-computer alias (default: "garnet:mock")
#   MQT_IQM_SHOTS         shots (default: 100 -- keep first runs small)

set -euo pipefail

SCRIPT_DIR=/mnt
MQT_CC_VENV="${MQT_CC_VENV:-/opt/openqse/mqt-cc-venv}"

: "${QFW_API_KEY:?set QFW_API_KEY to your IQM Resonance API token}"

echo "[$(date)] mqt-iqm on $(hostname)"

"${MQT_CC_VENV}/bin/python" "${SCRIPT_DIR}/mqt-iqm.py"

echo "[$(date)] mqt-iqm done on $(hostname)"
