#!/usr/bin/env python3
"""Run a GHZ circuit on the IBM Quantum System API simulator via QRMI with Qiskit."""

import os

from qiskit import QuantumCircuit
from qiskit.compiler import transpile

from qrmi import QuantumResource, ResourceType
from qrmi.primitives.ibm import SamplerV2, get_backend

base_url = os.environ.get("QFW_QC_URL", "http://ibmsim:8290")
alias = os.environ.get("QFW_QPU_DEVICE_ALIAS", "fake_lagos")
shots = int(os.environ.get("IBMSIM_TEST_SHOTS", "1024"))

# QRMI reads its IBM Quantum System settings from {backend}_QRMI_* variables.
# Every default matches docker-compose.ibmsim.yml.
settings = {
	"QRMI_IBM_QS_ENDPOINT": base_url,
	"QRMI_IBM_QS_IAM_ENDPOINT": base_url,
	"QRMI_IBM_QS_IAM_APIKEY": os.environ.get("QFW_API_KEY", "qfw-ibmsim-apikey"),
	"QRMI_IBM_QS_SERVICE_CRN": os.environ.get("IBMSIM_SERVICE_CRN",
		"crn:v1:bluemix:public:quantum-computing:us-east:a/qfw-ibmsim:qfw-ibmsim::"),
	"QRMI_IBM_QS_S3_ENDPOINT": os.environ.get("IBMSIM_S3_ENDPOINT", "http://ibmsim-s3:9000"),
	"QRMI_IBM_QS_S3_BUCKET": os.environ.get("IBMSIM_S3_BUCKET", "qfw-ibmsim"),
	"QRMI_IBM_QS_S3_REGION": os.environ.get("IBMSIM_S3_REGION", "us-east-1"),
	"QRMI_IBM_QS_AWS_ACCESS_KEY_ID": os.environ.get("QFW_IBM_AWS_ACCESS_KEY_ID", "qfw-ibmsim-access"),
	"QRMI_IBM_QS_AWS_SECRET_ACCESS_KEY": os.environ.get("QFW_IBM_AWS_SECRET_ACCESS_KEY", "qfw-ibmsim-secret"),
	"QRMI_JOB_TIMEOUT_SECONDS": "300",
}
for key, value in settings.items():
	os.environ.setdefault(f"{alias}_{key}", value)

# Open the simulated IBM device through QRMI.
qrmi = QuantumResource(alias, ResourceType.IBMQuantumSystem)
backend = get_backend(qrmi)
print(f"device: {backend.name} ({backend.num_qubits} qubits)")

# 3-qubit GHZ circuit.
circuit = QuantumCircuit(3, 3)
circuit.h(0)
circuit.cx(0, 1)
circuit.cx(1, 2)
circuit.measure([0, 1, 2], [0, 1, 2])

job = SamplerV2(qrmi).run([(transpile(circuit, backend),)], shots=shots)
counts = job.result()[0].data.c.get_counts()

print(f"counts: {dict(sorted(counts.items()))}")
