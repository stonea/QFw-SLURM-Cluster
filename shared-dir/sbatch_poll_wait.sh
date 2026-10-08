#!/bin/bash
#
# Submit an sbatch script and wait for it to finish by polling squeue, since
# `sbatch --wait` backs off to a 32s poll interval (see sbatch.c's
# _job_wait) and can leave you waiting well after the job is actually done.
#
# Run this where sbatch/squeue are already on PATH (e.g. an SSH'd-in cluster
# session) -- it runs as whatever user that shell is.

set -euo pipefail

POLL_INTERVAL="${POLL_INTERVAL:-1}"
export SBATCH_ACCOUNT="${SBATCH_ACCOUNT:-qfw-test}"

usage() {
    cat <<EOF
Usage: $(basename "$0") [sbatch-args...] <sbatch-script>

Submits <sbatch-script> (sbatch options must come before it, same as with
sbatch itself), polls squeue every ${POLL_INTERVAL}s until the job leaves the
queue, then cats its output file.

Environment:
  POLL_INTERVAL    Seconds between squeue polls (default: 1)
  SBATCH_ACCOUNT   Account to charge (default: qfw-test); pass --account on
                   the command line to override.
EOF
}

if [ "$#" -lt 1 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    usage
    [ "$#" -lt 1 ] && exit 1
    exit 0
fi

SCRIPT="${!#}"
SBATCH_ARGS=("${@:1:$#-1}")

CMD=(sbatch --parsable "${SBATCH_ARGS[@]}" "${SCRIPT}")
echo "+ ${CMD[*]}"
jobid="$("${CMD[@]}")"
jobid="${jobid%%;*}"   # --parsable prints "jobid;cluster" when --clusters is used
echo "Job ID: ${jobid}"

while [ -n "$(squeue -h -j "${jobid}" 2>/dev/null)" ]; do
    sleep "${POLL_INTERVAL}"
done

# Mirror Slurm's own %j/%J substitution to find the output file it wrote.
# No #SBATCH --output line is the normal case (default slurm-%j.out), so
# don't let grep's "no match" exit status trip `set -e`.
pattern="$(grep -m1 -oE '^#SBATCH[[:space:]]+(-o|--output)=?[[:space:]]*\S+' "${SCRIPT}" \
    | sed -E 's/^#SBATCH[[:space:]]+(-o|--output)=?[[:space:]]*//' || true)"
pattern="${pattern:-slurm-%j.out}"
outfile="${pattern//%[jJ]/${jobid}}"

echo "Job ${jobid} finished; output in ${outfile}"
if [ -f "${outfile}" ]; then
    cat "${outfile}"
fi
