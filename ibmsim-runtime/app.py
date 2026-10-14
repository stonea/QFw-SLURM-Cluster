"""Qiskit Runtime REST API front for the IBM Quantum System API simulator.

MQSC's IBM QDMI device library (ibm-qdmi-device) speaks the Qiskit Runtime
REST API of IBM Quantum Platform: a job is POSTed with its parameters inline
and answered with an id, its status is read from ``state.status`` and its
results from ``GET /v1/jobs/{id}/results``. The simulator (qsa_sim) speaks
IBM's Quantum System API instead, where the client chooses the job id and
hands over presigned S3 URLs that the job's input is read from and its
results and logs are written to. This service sits between the two: it
stages the parameters in the simulator's S3 store, submits the job in the
Quantum System shape, and serves status and results back in the Runtime
shape. The simulator stays the execution engine.

Only the subset the device library uses is served. Authentication is the
simulator's: the client's Authorization and Service-CRN headers are forwarded
and the simulator accepts or rejects them, and the IAM token endpoint is
forwarded too. This service's own credentials are the S3 key pair.

Everything is configured through the environment; the compose overlay sets
it. See docker-compose.ibmsim.yml.
"""

import json
import logging
import os
import uuid

import boto3
import httpx
from botocore.config import Config as BotoConfig
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

logging.basicConfig(level=os.environ.get("IBMSIM_RUNTIME_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ibmsim-runtime")

QSAPI_URL = os.environ.get("IBMSIM_QSAPI_URL", "http://ibmsim:8290").rstrip("/")
S3_ENDPOINT = os.environ.get("IBMSIM_S3_ENDPOINT", "http://ibmsim-s3:9000")
S3_BUCKET = os.environ.get("IBMSIM_S3_BUCKET", "qfw-ibmsim")
S3_REGION = os.environ.get("IBMSIM_S3_REGION", "us-east-1")
S3_ACCESS_KEY = os.environ.get("IBMSIM_S3_ACCESS_KEY", "qfw-ibmsim-access")
S3_SECRET_KEY = os.environ.get("IBMSIM_S3_SECRET_KEY", "qfw-ibmsim-secret")
# How long the presigned URLs handed to the simulator stay valid. The
# simulator reads the input when the job starts and writes results when it
# ends, so this bounds a job's queue plus run time.
PRESIGN_SECONDS = int(os.environ.get("IBMSIM_RUNTIME_PRESIGN_SECONDS", "86400"))
# The device library sends its job's maximum execution time as "cost"
# (60 s unless the caller raises it); it becomes the simulator's timeout_secs,
# which this floor keeps from cutting short a slow large-backend simulation.
MIN_TIMEOUT_SECS = int(os.environ.get("IBMSIM_RUNTIME_MIN_TIMEOUT_SECS", "300"))
VERSION = "0.1.0"

# Headers a Runtime client sends that the simulator checks. IBM-API-Version
# is Runtime-only and the simulator ignores unknown headers, so it is dropped.
FORWARDED_HEADERS = ("authorization", "service-crn")

# Quantum System API job statuses -> Runtime job statuses. The simulator runs
# a job as soon as it accepts it, so it has no queued state of its own.
STATUS_MAP = {
    "Running": "Running",
    "Completed": "Completed",
    "Failed": "Failed",
    "Cancelled": "Cancelled",
}

app = FastAPI(title="ibmsim-runtime", version=VERSION,
    description="Qiskit Runtime REST API front for the IBM Quantum System API simulator")

s3 = boto3.client("s3", endpoint_url=S3_ENDPOINT, region_name=S3_REGION,
    aws_access_key_id=S3_ACCESS_KEY, aws_secret_access_key=S3_SECRET_KEY,
    config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}))
upstream = httpx.Client(base_url=QSAPI_URL, timeout=httpx.Timeout(30.0))

# What the Runtime GET /v1/jobs/{id} answer needs that the simulator's job
# record does not carry: the parameters as submitted. They are also the S3
# input object, which is the fallback after a restart of this service.
_jobs = {}

# The simulator counts every job it still holds against its backend's
# execution lanes (five by default), finished or not, while Runtime frees a
# lane when the job ends. A Runtime client such as the device library never
# deletes its jobs, so after five runs a backend would refuse every new one
# with 429. So a job that has ended is deleted upstream as soon as this
# service sees it end, and its final record is kept here to keep answering
# for it; its results stay in S3. After a restart of this service, such a
# job is gone (404), as a deleted Runtime job is.
_finished = {}
FINAL_STATUSES = ("Completed", "Failed", "Cancelled")


def _forward_headers(request):
    return {name: value for name, value in request.headers.items()
        if name.lower() in FORWARDED_HEADERS}


def _relay(response):
    # Hand an upstream error back as it came, so a client sees the
    # simulator's own status code and message.
    media = response.headers.get("content-type", "application/json")
    return Response(content=response.content, status_code=response.status_code,
        media_type=media)


def _object_key(job_id, name):
    return f"{job_id}/{name}"


def _presign(method, key):
    return s3.generate_presigned_url(method, Params={"Bucket": S3_BUCKET, "Key": key},
        ExpiresIn=PRESIGN_SECONDS)


def _s3_get_json(key):
    body = s3.get_object(Bucket=S3_BUCKET, Key=key)["Body"].read()
    return json.loads(body)


@app.get("/version")
def version():
    try:
        qsapi = upstream.get("/version").json()
    except Exception as exc:  # noqa: BLE001 -- health answer, not a failure
        qsapi = {"error": str(exc)}
    return {"version": VERSION, "qsapi": qsapi, "qsapi_url": QSAPI_URL}


@app.post("/identity/token")
async def identity_token(request: Request):
    # IAM's apikey grant, as the device library posts it; the simulator
    # implements the same endpoint and shape.
    body = await request.body()
    response = upstream.post("/identity/token", content=body,
        headers={"content-type": request.headers.get("content-type",
            "application/x-www-form-urlencoded")})
    return _relay(response)


@app.get("/v1/backends/{backend}/configuration")
def backend_configuration(backend: str, request: Request):
    return _relay(upstream.get(f"/v1/backends/{backend}/configuration",
        headers=_forward_headers(request)))


@app.get("/v1/backends/{backend}/properties")
def backend_properties(backend: str, request: Request):
    return _relay(upstream.get(f"/v1/backends/{backend}/properties",
        headers=_forward_headers(request)))


@app.get("/v1/backends/{backend}/status")
def backend_status(backend: str, request: Request):
    # Runtime's status record from the simulator's backend details plus its
    # job list: the queue length is the number of jobs it is running there.
    headers = _forward_headers(request)
    details = upstream.get(f"/v1/backends/{backend}", headers=headers)
    if details.status_code != 200:
        return _relay(details)
    details = details.json()
    jobs = upstream.get("/v1/jobs", headers=headers)
    running = 0
    if jobs.status_code == 200:
        running = sum(1 for job in jobs.json().get("jobs", [])
            if job.get("backend") == backend and job.get("status") == "Running")
    online = details.get("status") == "online"
    return {
        "state": online,
        "status": "active" if online else "inactive",
        "message": details.get("message") or details.get("status", ""),
        "length_queue": running,
        "backend_version": details.get("version"),
    }


@app.post("/v1/jobs")
async def run_job(request: Request):
    # Runtime shape in: program_id, backend, params (inline), optional cost.
    # Quantum System shape out: our id, timeout_secs, storage with presigned
    # URLs; the parameters go to S3 first, where the simulator reads them.
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"errors": [{"message": "Body is not JSON"}]}, status_code=400)
    program_id = payload.get("program_id")
    backend = payload.get("backend")
    params = payload.get("params")
    if program_id not in ("sampler", "estimator") or not backend or params is None:
        return JSONResponse({"errors": [{"message":
            "program_id (sampler or estimator), backend and params are required"}]},
            status_code=400)
    job_id = str(uuid.uuid4())
    timeout_secs = max(int(payload.get("cost") or 0), MIN_TIMEOUT_SECS)

    input_key = _object_key(job_id, "params.json")
    s3.put_object(Bucket=S3_BUCKET, Key=input_key, Body=json.dumps(params).encode(),
        ContentType="application/json")
    job = {
        "id": job_id,
        "backend": backend,
        "program_id": program_id,
        "timeout_secs": timeout_secs,
        "storage": {
            "input": {"type": "s3_compatible",
                "presigned_url": _presign("get_object", input_key)},
            "results": {"type": "s3_compatible",
                "presigned_url": _presign("put_object", _object_key(job_id, "results.json"))},
            "logs": {"type": "s3_compatible",
                "presigned_url": _presign("put_object", _object_key(job_id, "logs.txt"))},
        },
    }
    if "log_level" in payload:
        job["log_level"] = payload["log_level"]
    response = upstream.post("/v1/jobs", json=job, headers=_forward_headers(request))
    if response.status_code != 204:
        logger.warning("job %s rejected by %s: %s %s", job_id, QSAPI_URL,
            response.status_code, response.text)
        return _relay(response)
    _jobs[job_id] = {"backend": backend, "program_id": program_id, "params": params}
    logger.info("job %s submitted: %s on %s", job_id, program_id, backend)
    return {"id": job_id, "backend": backend}


def _runtime_job(record):
    # The simulator's job record in Runtime's JobResponse shape, as far as the
    # device library reads it.
    job_id = record["id"]
    known = _jobs.get(job_id)
    if known is None:
        try:
            params = _s3_get_json(_object_key(job_id, "params.json"))
        except Exception:  # noqa: BLE001 -- a job this service did not submit
            params = None
        known = {"backend": record.get("backend"),
            "program_id": record.get("program_id"), "params": params}
        _jobs[job_id] = known
    status = STATUS_MAP.get(record.get("status"), "Failed")
    state = {"status": status}
    reason = record.get("reason_message")
    if reason:
        state["reason"] = reason
    if record.get("reason_code") is not None:
        state["reason_code"] = record["reason_code"]
    return {
        "id": job_id,
        "backend": known["backend"],
        "program": {"id": known["program_id"]},
        "params": known["params"],
        "state": state,
        "status": status,
        "private": False,
        "created": record.get("created_time"),
        "ended": record.get("end_time"),
        "usage": record.get("metrics"),
    }


def _job_record(job_id, request):
    # The simulator's record for a job, as (record, None), or (None, the
    # upstream error to relay). A job seen ending is deleted upstream to free
    # its lane, and served from _finished from then on.
    record = _finished.get(job_id)
    if record is not None:
        return record, None
    headers = _forward_headers(request)
    response = upstream.get(f"/v1/jobs/{job_id}", headers=headers)
    if response.status_code != 200:
        return None, _relay(response)
    record = response.json()
    if record.get("status") in FINAL_STATUSES:
        _finished[job_id] = record
        deleted = upstream.delete(f"/v1/jobs/{job_id}", headers=headers)
        if deleted.status_code == 204:
            logger.info("job %s %s; deleted upstream to free its lane",
                job_id, record["status"].lower())
        else:
            logger.warning("job %s %s, but deleting it upstream failed: %s %s",
                job_id, record["status"].lower(), deleted.status_code, deleted.text)
    return record, None


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    record, error = _job_record(job_id, request)
    if error is not None:
        return error
    return _runtime_job(record)


@app.get("/v1/jobs/{job_id}/results")
def get_results(job_id: str, request: Request):
    # Results live in S3, written by the simulator through the presigned URL.
    # Runtime answers 204 while they are not there yet.
    record, error = _job_record(job_id, request)
    if error is not None:
        return error
    if record.get("status") != "Completed":
        if record.get("status") in ("Failed", "Cancelled"):
            return JSONResponse({"errors": [{"message":
                f"job {job_id} {record['status'].lower()}: "
                f"{record.get('reason_message') or 'no results'}"}]}, status_code=409)
        return Response(status_code=204)
    try:
        body = s3.get_object(Bucket=S3_BUCKET,
            Key=_object_key(job_id, "results.json"))["Body"].read()
    except s3.exceptions.NoSuchKey:
        return Response(status_code=204)
    return Response(content=body, media_type="application/json")


@app.post("/v1/jobs/{job_id}/cancel")
def cancel_job(job_id: str, request: Request):
    if job_id in _finished:
        return JSONResponse({"errors": [{"message":
            f"job {job_id} has already ended"}]}, status_code=409)
    response = upstream.post(f"/v1/jobs/{job_id}/cancel", headers=_forward_headers(request))
    if response.status_code == 204:
        return Response(status_code=204)
    return _relay(response)


@app.delete("/v1/jobs/{job_id}")
def delete_job(job_id: str, request: Request):
    if _finished.pop(job_id, None) is not None:
        # Already deleted upstream when it ended.
        _jobs.pop(job_id, None)
        return Response(status_code=204)
    response = upstream.delete(f"/v1/jobs/{job_id}", headers=_forward_headers(request))
    if response.status_code == 204:
        _jobs.pop(job_id, None)
        return Response(status_code=204)
    return _relay(response)
