# Qiskit Runtime REST API front for the IBM Quantum System API simulator
# (app.py): what lets MQSC's IBM QDMI device library, which speaks IBM
# Quantum Platform's API, reach the simulator, which speaks IBM's Quantum
# System API. See docker-compose.ibmsim.yml.

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py tls.sh /app/

# The port, simulator address and S3 settings come from the environment at
# run time; the compose overlay sets them. tls.sh issues the HTTPS
# certificate at every start (openssl comes with the base image's
# ca-certificates) and publishes its CA to /tls.
CMD ["sh", "-c", "sh /app/tls.sh && exec uvicorn app:app --host 0.0.0.0 --port ${IBMSIM_RUNTIME_BIND_PORT:-8291} --ssl-keyfile /run/ibmsim-tls/server.key --ssl-certfile /run/ibmsim-tls/server.crt"]
