#!/bin/bash
#
#SBATCH --job-name=mqt-ddsim
#SBATCH --time=00:05:00
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=512M
#
# Compile a GHZ circuit to QIR with MQT and run it on the local DDSIM
# simulator through QDMI. Needs no credentials, network, or QPU allocation.
# The actual work is in mqt-ddsim.py alongside this script.

set -euo pipefail

SCRIPT_DIR=/mnt
MQT_CC_VENV="${MQT_CC_VENV:-/opt/openqse/mqt-cc-venv}"

echo "[$(date)] mqt-ddsim on $(hostname)"

# mqt-cc-venv has the MLIR compiler bindings (mqt.core.mlir) needed to emit
# QIR; QFw's own venv only carries the mqt-core PyPI wheel.
"${MQT_CC_VENV}/bin/python" "${SCRIPT_DIR}/mqt-ddsim.py"

echo "[$(date)] mqt-ddsim done on $(hostname)"
