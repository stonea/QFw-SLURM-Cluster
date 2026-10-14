#!/usr/bin/env python3
"""Run a GHZ circuit on the IBM Quantum System API simulator via QDMI (MQT Core) with Qiskit."""

import os

from qiskit import QuantumCircuit
from qiskit.compiler import transpile

from mqt.core.plugins.qiskit import QDMIBackend
from mqt.core.plugins.qiskit.serializers import register_program_serializer
from mqt.core.qdmi import ProgramFormat
from mqt.core.qdmi.driver import DeviceDefinition, register_device_if_absent
from ibm.qdmi import IBM_QDMI_DEVICE_ID, IBM_QDMI_LIBRARY_PATH, IBM_QDMI_PREFIX
from ibm.qdmi.serializers import qiskit_to_qasm3

base_url = os.environ.get("IBMSIM_RUNTIME_URL", "https://ibmsim-runtime:8291").rstrip("/")
api_key = os.environ.get("QFW_API_KEY", "qfw-ibmsim-apikey")
crn = os.environ.get("IBMSIM_SERVICE_CRN",
	"crn:v1:bluemix:public:quantum-computing:us-east:a/qfw-ibmsim:qfw-ibmsim::")
alias = os.environ.get("QFW_QPU_DEVICE_ALIAS", "fake_lagos")
shots = int(os.environ.get("IBMSIM_TEST_SHOTS", "1024"))

# Open the simulated IBM device through MQT Core's QDMI driver.
register_device_if_absent(DeviceDefinition(IBM_QDMI_DEVICE_ID, IBM_QDMI_LIBRARY_PATH, IBM_QDMI_PREFIX))
backend = QDMIBackend.from_device_id(IBM_QDMI_DEVICE_ID, base_url=base_url,
	auth_url=f"{base_url}/identity/token", token=api_key, custom1=alias, custom2=crn)
print(f"device: {backend.name} ({backend.num_qubits} qubits)")

# IBM's OpenQASM 3 importer rejects the classical-bit initialization MQT Core's
# default serializer emits, so export the way IBM's device package does.
register_program_serializer(ProgramFormat.QASM3,
	lambda circuit, backend: qiskit_to_qasm3(circuit, backend.num_qubits), replace=True)

# 3-qubit GHZ circuit.
circuit = QuantumCircuit(3, 3)
circuit.h(0)
circuit.cx(0, 1)
circuit.cx(1, 2)
circuit.measure([0, 1, 2], [0, 1, 2])

job = backend.sampler().run([(transpile(circuit, backend),)], shots=shots)
counts = job.result()[0].data.c.get_counts()

print(f"counts: {dict(sorted(counts.items()))}")
