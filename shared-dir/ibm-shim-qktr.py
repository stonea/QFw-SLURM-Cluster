#!/usr/bin/env python3
"""Build a GHZ circuit with Qiskit and run it through QFw's QRMI/QDMI shim
(services/svc_lib_qpm), used directly as a Python module -- no QPM service,
no DEFw RPC. Targets the IBM Quantum System API simulator started by
docker-compose.ibmsim.yml, the same target ibm-qrmi-qktr.py and
ibm-qdmi-qktr.py use, so this needs no IBM account.

The IBM counterpart of iqm-shim-qktr.py: it transpiles with Qiskit's own
transpile() against IBM's QDMI device as a Qiskit backend."""

import os
from types import SimpleNamespace

from qiskit import QuantumCircuit
from qiskit.compiler import transpile

from mqt.core.plugins.qiskit import QDMIBackend
from mqt.core.qdmi.driver import DeviceDefinition, register_device_if_absent
from ibm.qdmi import IBM_QDMI_DEVICE_ID, IBM_QDMI_LIBRARY_PATH, IBM_QDMI_PREFIX

import defw  # noqa: F401  -- puts DEFw's service-apis on sys.path
from svc_lib_qpm.descriptor import (
	DEFAULT_CAPS, DEFAULT_EXECUTION_OWNER, DEFAULT_LIBRARIES, DEFAULT_PREFERENCE)
from svc_lib_qpm.drivers import QdmiDriver, QrmiDriver
from svc_lib_qpm.frontend import Frontend
from util.circuit_payload import encode_qiskit_circuit, qiskit_circuit_formats

# Drivers' _access() read QFW_QC_URL/QFW_API_KEY from the environment when the
# descriptor names no device-access config entry (drivers/qdmi_driver.py,
# drivers/qrmi_driver.py); setdefault puts the resolved default back so that
# holds. The S3 key pair is a secret, so QRMI reads it from QFW_IBM_AWS_*
# rather than the descriptor. Every default matches docker-compose.ibmsim.yml.
base_url = os.environ.setdefault("QFW_QC_URL", "http://ibmsim:8290")
token = os.environ.setdefault("QFW_API_KEY", "qfw-ibmsim-apikey")
os.environ.setdefault("QFW_IBM_AWS_ACCESS_KEY_ID", "qfw-ibmsim-access")
os.environ.setdefault("QFW_IBM_AWS_SECRET_ACCESS_KEY", "qfw-ibmsim-secret")
runtime_url = os.environ.get("IBMSIM_RUNTIME_URL", "https://ibmsim-runtime:8291").rstrip("/")
crn = os.environ.get("IBMSIM_SERVICE_CRN",
	"crn:v1:bluemix:public:quantum-computing:us-east:a/qfw-ibmsim:qfw-ibmsim::")
alias = os.environ.get("QFW_QPU_DEVICE_ALIAS", "fake_lagos")
shots = int(os.environ.get("SHIM_TEST_SHOTS", "1024"))
timeout = float(os.environ.get("SHIM_TEST_TIMEOUT", "300"))
lib = os.environ.get("SHIM_TEST_LIB") or None  # "qrmi", "qdmi", or descriptor's choice

# A synthetic descriptor for the simulated device (no device-access config
# entry names it); libraries/caps/preference/owner mirror descriptor.py's own
# defaults. QRMI's IBMQuantumSystem reaches the simulator's Quantum System API
# at QFW_QC_URL, with IAM there too and results staged through S3. QDMI's IBM
# device library speaks the Qiskit Runtime API instead, so it goes through the
# overlay's Runtime front, which also serves IAM.
descriptor = {
	"id": "ibm-qsa-sim",
	"provider": "ibm",
	"resource_type": "IBMQuantumSystem",
	"provider_device_id": alias,
	"service_crn": crn,
	"iam_endpoint": base_url,
	"s3_endpoint": os.environ.get("IBMSIM_S3_ENDPOINT", "http://ibmsim-s3:9000"),
	"s3_bucket": os.environ.get("IBMSIM_S3_BUCKET", "qfw-ibmsim"),
	"s3_region": os.environ.get("IBMSIM_S3_REGION", "us-east-1"),
	"job_timeout_seconds": int(timeout),
	"runtime_endpoint": runtime_url,
	"runtime_auth_url": f"{runtime_url}/identity/token",
	"libraries": list(DEFAULT_LIBRARIES),
	"preference": DEFAULT_PREFERENCE,
	"execution_owner": DEFAULT_EXECUTION_OWNER,
	"caps": {call: list(libs) for call, libs in DEFAULT_CAPS.items()},
}
frontend = Frontend([QrmiDriver(descriptor), QdmiDriver(descriptor)], descriptor)

# 3-qubit GHZ circuit.
circuit = QuantumCircuit(3, 3)
circuit.h(0)
circuit.cx(0, 1)
circuit.cx(1, 2)
circuit.measure([0, 1, 2], [0, 1, 2])

# IBM hardware only runs its own native gate set (no h); transpile against
# the device, before handing the circuit to the shim. Both drivers recognize
# the result as already native and keep the layout transpile() chose.
register_device_if_absent(DeviceDefinition(IBM_QDMI_DEVICE_ID, IBM_QDMI_LIBRARY_PATH, IBM_QDMI_PREFIX))
backend = QDMIBackend.from_device_id(IBM_QDMI_DEVICE_ID, base_url=runtime_url,
	auth_url=f"{runtime_url}/identity/token", token=token, custom1=alias, custom2=crn)
circuit = transpile(circuit, backend)

# Send the circuit as QPY rather than OpenQASM 2, so the drivers load this
# QuantumCircuit directly instead of re-parsing QASM text. QRMI's IBM path
# requires QPY. Both drivers read circuits through Qiskit, and
# qiskit_circuit_formats() is exactly what svc_lib_qpm/svc_qpm.py advertises
# for that (qpy+gzip first), so this is the format a client would negotiate
# through the real QPM service.
info = {
	"num_shots": shots,
	"timeout": timeout,
	**encode_qiskit_circuit(circuit, qiskit_circuit_formats()),
}

job = SimpleNamespace(info=info)

used = frontend.route("run_circuit", lib=lib).name
print(f"device: {descriptor['id']} ({descriptor['provider']}:{alias})")
print(f"routing run_circuit -> {used}")
print(f"circuit format: {(info.get('circuit') or {}).get('format', 'openqasm2')}")

result = frontend.run_circuit(job, lib=lib)
counts = (result.get("result") or {}).get("counts") or result.get("counts") or {}

print(f"counts: {dict(sorted(counts.items()))}")
