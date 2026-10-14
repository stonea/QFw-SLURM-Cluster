#!/usr/bin/env python3
"""Build a GHZ circuit with Qiskit and run it through QFw's QRMI/QDMI shim
(services/svc_lib_qpm), used directly as a Python module -- no QPM service,
no DEFw RPC. Targets IQM Resonance's free `garnet:mock` backend by default,
the same target iqm-qdmi-qktr.py uses, so this needs only a Resonance API token."""

import base64
import io
import os
import subprocess
import tempfile
from types import SimpleNamespace

from qiskit import QuantumCircuit, qpy

import defw  # noqa: F401  -- puts DEFw's service-apis on sys.path
from svc_lib_qpm.descriptor import (
	DEFAULT_CAPS, DEFAULT_EXECUTION_OWNER, DEFAULT_LIBRARIES, DEFAULT_PREFERENCE)
from svc_lib_qpm.drivers import QdmiDriver, QrmiDriver
from svc_lib_qpm.frontend import Frontend
from util.circuit_payload import QPY

# Drivers' _access() read QFW_QC_URL/QFW_API_KEY from the environment when the
# descriptor names no device-access config entry (drivers/qdmi_driver.py,
# drivers/qrmi_driver.py); setdefault puts the resolved default back so that holds.
base_url = os.environ.setdefault("QFW_QC_URL", "https://resonance.iqm.tech/")
token = os.environ["QFW_API_KEY"]
alias = os.environ.get("QFW_QPU_DEVICE_ALIAS", "garnet:mock")
shots = int(os.environ.get("SHIM_TEST_SHOTS", "100"))
# The mock backend can queue past both drivers' 300s default poll timeout.
timeout = float(os.environ.get("SHIM_TEST_TIMEOUT", "600"))
lib = os.environ.get("SHIM_TEST_LIB") or None  # "qrmi", "qdmi", or descriptor's choice
mqt_cc_venv = os.environ.get("MQT_CC_VENV", "/opt/openqse/mqt-cc-venv")
mqt_model = os.environ.get("SHIM_TEST_MQT_MODEL", "mqt.sc.iqm.garnet")

# A synthetic descriptor for Resonance's mock device (no device-access config
# entry names it); libraries/caps/preference/owner mirror descriptor.py's own defaults.
descriptor = {
	"id": "iqm-resonance-mock",
	"provider": "iqm",
	"provider_device_id": alias,
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

# IQM hardware only runs its own native gate set (no h/cx); transpile with
# mqt-cc against its bundled Garnet model before handing the circuit to the
# shim. The qfw venv's mqt-core has no compiler, so the compile runs in the
# mqt-cc venv, via mqt-cc-transpile.py, with QPY files carrying the circuit
# each way.
with tempfile.TemporaryDirectory() as tmp_dir:
	input_file = os.path.join(tmp_dir, "input.qpy")
	output_file = os.path.join(tmp_dir, "output.qpy")
	with open(input_file, "wb") as f:
		qpy.dump(circuit, f)
	# qfw-activate's PYTHONPATH would shadow the mqt-cc venv's own mqt.core.
	child_env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
	subprocess.run(
		[os.path.join(mqt_cc_venv, "bin", "python"),
		 os.path.join(os.path.dirname(os.path.abspath(__file__)), "mqt-cc-transpile.py"),
		 "--input", input_file, "--model", mqt_model,
		 "--qpy-version", str(qpy.QPY_VERSION), "--output", output_file],
		env=child_env, check=True)
	with open(output_file, "rb") as f:
		qpy_bytes = f.read()
circuit = qpy.load(io.BytesIO(qpy_bytes))[0]
print(f"mqt-cc transpiled for {mqt_model}: {dict(circuit.count_ops())}")

# Hand mqt-cc's QPY to the shim as-is rather than re-encoding it; it was
# written at this interpreter's QPY_VERSION, so the drivers can load it.
info = {"num_shots": shots, "timeout": timeout,
		"circuit": {"format": QPY, "data": base64.b64encode(qpy_bytes).decode("ascii")}}
job = SimpleNamespace(info=info)

used = frontend.route("run_circuit", lib=lib).name
print(f"device: {descriptor['id']} ({descriptor['provider']}:{alias})")
print(f"routing run_circuit -> {used}")

result = frontend.run_circuit(job, lib=lib)
counts = (result.get("result") or {}).get("counts") or result.get("counts") or {}

print(f"counts: {dict(sorted(counts.items()))}")
