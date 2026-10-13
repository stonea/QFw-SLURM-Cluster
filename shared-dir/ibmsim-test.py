#!/usr/bin/env python3
"""Build a GHZ circuit with Qiskit and run it through QFw's QRMI/QDMI shim
(services/svc_lib_qpm), used directly as a Python module -- no QPM service,
no DEFw RPC -- against the IBM Quantum System API simulator started by
docker-compose.ibmsim.yml. QRMI's IBMQuantumSystem resource is the client,
exactly as it would be for a real IBM system; only the addresses differ.
No IBM account, no network, no cost."""

import base64
import io
import os
from types import SimpleNamespace

from qiskit import QuantumCircuit, qpy

import defw  # noqa: F401  -- puts DEFw's service-apis on sys.path
from svc_lib_qpm.drivers import QrmiDriver
from svc_lib_qpm.frontend import Frontend
from util.circuit_payload import QPY

# The driver's _access() reads QFW_QC_URL/QFW_API_KEY from the environment
# when the descriptor names no device-access config entry; setdefault puts
# the resolved defaults back so that holds. The S3 key pair is a secret in
# the driver's model, so it comes from QFW_IBM_AWS_* rather than the
# descriptor. Every default matches docker-compose.ibmsim.yml.
base_url = os.environ.setdefault("QFW_QC_URL", "http://ibmsim:8290")
os.environ.setdefault("QFW_API_KEY", "qfw-ibmsim-apikey")
os.environ.setdefault("QFW_IBM_AWS_ACCESS_KEY_ID", "qfw-ibmsim-access")
os.environ.setdefault("QFW_IBM_AWS_SECRET_ACCESS_KEY", "qfw-ibmsim-secret")
alias = os.environ.get("QFW_QPU_DEVICE_ALIAS", "fake_lagos")
shots = int(os.environ.get("IBMSIM_TEST_SHOTS", "1024"))
timeout = float(os.environ.get("IBMSIM_TEST_TIMEOUT", "300"))

# A synthetic descriptor for the simulated device. provider ibm serves three
# QRMI resource types, so resource_type picks the one the simulator emulates.
# The IAM endpoint, service CRN and object store belong to the device, so
# they are descriptor keys; the driver reads them where device-access config
# would otherwise supply them. The simulator fronts Aer, so there is no QDMI
# leg: one library, wired, preferred and owning execution.
descriptor = {
	"id": "ibm-qsa-sim",
	"provider": "ibm",
	"resource_type": "IBMQuantumSystem",
	"provider_device_id": alias,
	"iam_endpoint": base_url,
	"service_crn": os.environ.get("IBMSIM_SERVICE_CRN", "crn:v1:local:qfw-ibmsim"),
	"s3_endpoint": os.environ.get("IBMSIM_S3_ENDPOINT", "http://ibmsim-s3:9000"),
	"s3_bucket": os.environ.get("IBMSIM_S3_BUCKET", "qfw-ibmsim"),
	"s3_region": os.environ.get("IBMSIM_S3_REGION", "us-east-1"),
	# QRMI_JOB_TIMEOUT_SECONDS, which IBMQuantumSystem requires; the driver's
	# own poll deadline is info["timeout"] below. Keep them equal so neither
	# side abandons a job the other is still waiting on.
	"job_timeout_seconds": int(timeout),
	"libraries": ["qrmi"],
	"preference": "qrmi",
	"execution_owner": "qrmi",
	"caps": {"run_circuit": ["qrmi"], "get_device_info": ["qrmi"],
		"get_coupling_graph": ["qrmi"]},
}
frontend = Frontend([QrmiDriver(descriptor)], descriptor)

# 3-qubit GHZ circuit.
circuit = QuantumCircuit(3, 3)
circuit.h(0)
circuit.cx(0, 1)
circuit.cx(1, 2)
circuit.measure([0, 1, 2], [0, 1, 2])

# The IBM path requires QPY (it keeps everything OpenQASM 2 would drop), and
# the driver transpiles to the backend's ISA itself, from the configuration
# and properties QRMI's target() fetches from the simulator.
buf = io.BytesIO()
qpy.dump(circuit, buf)
info = {"num_shots": shots, "timeout": timeout,
		"circuit": {"format": QPY, "data": base64.b64encode(buf.getvalue()).decode("ascii")}}
job = SimpleNamespace(info=info)

device = frontend.get_device_info()
num_qubits = (device.get("device") or {}).get("num_qubits")
print(f"device: {descriptor['id']} ({descriptor['provider']}:{alias}), "
	f"{num_qubits} qubits via {frontend.route('get_device_info').name}")
print(f"routing run_circuit -> {frontend.route('run_circuit').name}")

result = frontend.run_circuit(job)
counts = (result.get("result") or {}).get("counts") or result.get("counts") or {}
counts = dict(sorted(counts.items()))
print(f"counts: {counts}")

# Aer runs with the fake backend's noise model, and some of these snapshots
# are noisy (FakeLagos leaves ~70% in the GHZ states), so the check is that
# |000> and |111> are the two most frequent outcomes and hold a majority.
total = sum(counts.values())
ghz = counts.get("000", 0) + counts.get("111", 0)
top_two = sorted(counts, key=counts.get, reverse=True)[:2]
print(f"GHZ fidelity proxy: {ghz}/{total} shots in |000> + |111>")
if total != shots or set(top_two) != {"000", "111"} or ghz <= 0.5 * shots:
	raise SystemExit(
		f"IBMSIM GHZ TEST: FAIL (expected {shots} shots with 000 and 111 the two "
		"most frequent outcomes and a majority between them)")
print("IBMSIM GHZ TEST: PASS")
