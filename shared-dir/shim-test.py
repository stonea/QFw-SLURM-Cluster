#!/usr/bin/env python3
"""Build a GHZ circuit with Qiskit and run it through QFw's QRMI/QDMI shim
(services/svc_lib_qpm), used directly as a Python module -- no QPM service,
no DEFw RPC. Targets IQM Resonance's free `garnet:mock` backend by default,
the same target mqt-iqm.py uses, so this needs only a Resonance API token."""

import os
from types import SimpleNamespace

from qiskit import QuantumCircuit
from qiskit.compiler import transpile

from iqm.qdmi.qiskit import IQMBackend

import defw  # noqa: F401  -- puts DEFw's service-apis on sys.path
from svc_lib_qpm.descriptor import (
	DEFAULT_CAPS, DEFAULT_EXECUTION_OWNER, DEFAULT_LIBRARIES, DEFAULT_PREFERENCE)
from svc_lib_qpm.drivers import QdmiDriver, QrmiDriver
from svc_lib_qpm.frontend import Frontend
from util.circuit_payload import encode_qiskit_circuit

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

# IQM hardware only runs its own native gate set (no h/cx); transpile against
# the real device, before handing the circuit to the shim.
backend = IQMBackend(base_url=base_url, qc_alias=alias, token=token)
circuit = transpile(circuit, backend)

info = {"num_shots": shots, "timeout": timeout, **encode_qiskit_circuit(circuit)}
job = SimpleNamespace(info=info)

used = frontend.route("run_circuit", lib=lib).name
print(f"device: {descriptor['id']} ({descriptor['provider']}:{alias})")
print(f"routing run_circuit -> {used}")

result = frontend.run_circuit(job, lib=lib)
counts = (result.get("result") or {}).get("counts") or result.get("counts") or {}

print(f"counts: {dict(sorted(counts.items()))}")
