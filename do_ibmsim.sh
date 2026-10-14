#!/bin/bash
#
# Start, stop or inspect the IBM Quantum System API simulator beside the
# running cluster: the simulator, its S3 store, the bucket-creating one-shot
# and the Qiskit Runtime API front for QDMI clients, all from
# docker-compose.ibmsim.yml. The cluster's own containers are never recreated
# by this script.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/qfw-install.env"
SERVICES=(ibmsim-s3 ibmsim-s3-init ibmsim ibmsim-runtime)

usage() {
    cat <<USAGE
Usage: $(basename "$0") ACTION [compose arguments]

Actions:
  up        Build the simulator and Runtime-front images on first use and
            start the stack
  down      Stop and remove its containers, keeping the S3 volume
  purge     down, then remove the S3 volume
  rebuild   Rebuild the simulator image (after changing IBMSIM_REF) and the
            Runtime front (after editing ibmsim-runtime/), then restart both
  status    Show its containers
  logs      Follow its logs (extra arguments go to docker compose logs)
  url       Print where the simulator's and the Runtime front's API docs are

Nothing in the cluster has to change for a job to reach the simulator:
shared-dir/ibm-qrmi-qktr.sbatch (QRMI), shared-dir/ibm-qdmi-qktr.sbatch
(QDMI, via ibmsim-runtime) and shared-dir/ibm-shim-qktr.sbatch (either,
through the QFw shim) default to the addresses and placeholder
credentials the overlay uses. To start the stack with the cluster instead,
configure the overlay in with ./do_configure.sh --ibmsim before ./do_startup.sh.
See docker-compose.ibmsim.yml.
USAGE
}

if [ ! -f "${ENV_FILE}" ]; then
    echo "Missing ${ENV_FILE}. Run ./do_configure.sh first." >&2
    exit 1
fi

# The same files the cluster runs with, plus the overlay. Compose only
# includes docker-compose.override.yml on its own when no -f is given, so
# it is named here when present; otherwise compose would see a different
# configuration for the cluster's services.
FILES=(-f "${SCRIPT_DIR}/docker-compose.yml")
if [ -f "${SCRIPT_DIR}/docker-compose.override.yml" ]; then
    FILES+=(-f "${SCRIPT_DIR}/docker-compose.override.yml")
fi
FILES+=(-f "${SCRIPT_DIR}/docker-compose.ibmsim.yml")
COMPOSE=(docker compose --env-file "${ENV_FILE}" --project-directory "${SCRIPT_DIR}" "${FILES[@]}")

env_port() {
    # $1: variable name in the env file, $2: its value in the environment,
    # $3: default; the environment wins over the env file.
    local port="$2"
    if [ -z "${port}" ]; then
        port="$(awk -F= -v name="$1" '$1 == name { print $2 }' "${ENV_FILE}" | tail -n 1)"
    fi
    echo "${port:-$3}"
}

ibmsim_port() {
    env_port IBMSIM_PORT "${IBMSIM_PORT:-}" 8290
}

ibmsim_runtime_port() {
    env_port IBMSIM_RUNTIME_PORT "${IBMSIM_RUNTIME_PORT:-}" 8291
}

project_name() {
    "${COMPOSE[@]}" config --format json 2>/dev/null \
        | python3 -c 'import json, sys; print(json.load(sys.stdin)["name"])'
}

action="${1:-}"
shift || true
case "${action}" in
    up)
        "${COMPOSE[@]}" up -d --no-recreate "${SERVICES[@]}" "$@"
        echo "Simulator API docs:     http://localhost:$(ibmsim_port)/docs  (in-cluster: http://ibmsim:8290)"
        echo "Runtime front API docs: https://localhost:$(ibmsim_runtime_port)/docs  (in-cluster: https://ibmsim-runtime:8291)"
        echo "Runtime front CA:       shared-dir/ibmsim-tls/ca.crt  (in-cluster: /mnt/ibmsim-tls/ca.crt)"
        echo "Submit shared-dir/ibm-qrmi-qktr.sbatch (QRMI), shared-dir/ibm-qdmi-qktr.sbatch (QDMI)"
        echo "or shared-dir/ibm-shim-qktr.sbatch (QRMI or QDMI through the QFw shim)"
        echo "from slurmctld to run a GHZ circuit on it."
        ;;
    down)
        "${COMPOSE[@]}" rm --stop --force "${SERVICES[@]}" "$@"
        ;;
    purge)
        "${COMPOSE[@]}" rm --stop --force "${SERVICES[@]}"
        project="$(project_name)"
        if [ -z "${project}" ]; then
            echo "Could not determine the compose project name; volume not removed." >&2
            exit 1
        fi
        docker volume rm "${project}_ibmsim_s3_data"
        ;;
    rebuild)
        "${COMPOSE[@]}" build --no-cache ibmsim ibmsim-runtime "$@"
        "${COMPOSE[@]}" up -d --force-recreate ibmsim ibmsim-runtime
        ;;
    status)
        "${COMPOSE[@]}" ps -a "${SERVICES[@]}" "$@"
        ;;
    logs)
        "${COMPOSE[@]}" logs --follow --tail=100 "${SERVICES[@]}" "$@"
        ;;
    url)
        echo "http://localhost:$(ibmsim_port)/docs"
        echo "https://localhost:$(ibmsim_runtime_port)/docs"
        ;;
    -h|--help|help|"")
        usage
        [ -n "${action}" ] || exit 1
        ;;
    *)
        echo "Unknown action: ${action}" >&2
        usage >&2
        exit 1
        ;;
esac
