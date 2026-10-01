#!/usr/bin/env python3
"""Discover a live IQM QPU via QDMI (MQT Core) and run a GHZ circuit on it with Qiskit."""

import os

from qiskit import QuantumCircuit
from qiskit.compiler import transpile

from mqt.core.qdmi.driver import DeviceDefinition, open_device, register_device_if_absent
from iqm.qdmi import IQM_QDMI_DEVICE_ID, IQM_QDMI_LIBRARY_PATH
from iqm.qdmi.qiskit import IQMBackend

base_url = os.environ.get("QFW_QC_URL", "https://resonance.iqm.tech/")
token = os.environ["QFW_API_KEY"]
alias = os.environ.get("QFW_QPU_DEVICE_ALIAS", "garnet:mock")
shots = int(os.environ.get("MQT_IQM_SHOTS", "100"))

# Discover the live IQM device through MQT Core's QDMI driver.
register_device_if_absent(DeviceDefinition(IQM_QDMI_DEVICE_ID, IQM_QDMI_LIBRARY_PATH, "IQM"))
device = open_device(IQM_QDMI_DEVICE_ID, base_url=base_url, token=token, custom2=alias)
print(f"device: {device.name()} ({device.qubits_num()} qubits)")

# 3-qubit GHZ circuit.
circuit = QuantumCircuit(3, 3)
circuit.h(0)
circuit.cx(0, 1)
circuit.cx(1, 2)
circuit.measure([0, 1, 2], [0, 1, 2])

# IQM's QIR parser rejects the QIR mqt-cc emits, so submit through IQM's own
# Qiskit backend instead of QDMI's submit_job.
backend = IQMBackend(base_url=base_url, qc_alias=alias, token=token)
job = backend.sampler().run([(transpile(circuit, backend),)], shots=shots)
counts = job.result()[0].data.c.get_counts()

print(f"counts: {dict(sorted(counts.items()))}")
