# The IBM Quantum System API simulator (qsa_sim) from
# qrmi-community/simulated_quantum_resource: a local, offline stand-in for
# IBM's Quantum System API with Qiskit Aer behind it. QRMI's IBMQuantumSystem
# resource talks to it unchanged, so the shim's IBM execution path can be
# exercised with no IBM account and no cost. See docker-compose.ibmsim.yml.
#
# Lives in its own directory so the build context is just this file, not the
# repository root with the shared mount under it.
#
# Upstream ships a Dockerfile that COPYs a checkout; this one clones the
# pinned ref instead, so the cluster repository carries no copy of the
# simulator's sources, the same way the cluster image obtains QFw.

FROM python:3.12-slim

ARG IBMSIM_REPOSITORY=https://github.com/qrmi-community/simulated_quantum_resource.git
ARG IBMSIM_REF=0d547e7d329b8bd3315392e9117f116dc1661ddd

WORKDIR /app

RUN set -ex \
    && apt-get update \
    && apt-get install -y --no-install-recommends git \
    && git clone "${IBMSIM_REPOSITORY}" /tmp/qsa_sim \
    && git -C /tmp/qsa_sim checkout "${IBMSIM_REF}" \
    && cp -r /tmp/qsa_sim/qsa_sim /tmp/qsa_sim/config.yaml /tmp/qsa_sim/requirements.txt /tmp/qsa_sim/VERSION.txt /app/ \
    && rm -rf /tmp/qsa_sim \
    && apt-get purge -y git \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

# Port, API key and service CRN come from the environment at run time
# (QSASIM_BIND_PORT, QSASIM_IAM_APIKEY, QSASIM_SERVICE_CRN); the compose
# overlay sets them. config.yaml's own iam_apikeys stay accepted as well.
CMD ["python", "-m", "qsa_sim.app", "config.yaml"]
