#!/usr/bin/env python3
"""Build a GHZ circuit with Qiskit, compile it with MQT, and run it on DDSIM via QDMI."""

from qiskit import QuantumCircuit

from mqt.core.mlir import CompilerTarget, compile_program
from mqt.core.qdmi import ProgramFormat
from mqt.core.qdmi.driver import open_device

shots = 1024

# 3-qubit GHZ circuit.
circuit = QuantumCircuit(3, 3)
circuit.h(0)
circuit.cx(0, 1)
circuit.cx(1, 2)
circuit.measure([0, 1, 2], [0, 1, 2])

# DDSIM ships with MQT Core as a bundled, pre-registered QDMI device.
device = open_device("mqt.ddsim.default")
print(f"device: {device.name()}")

# Compile Qiskit -> MQT -> QIR for the device's own compiler target.
target = CompilerTarget.from_device(device)
compiled = compile_program(circuit, target=target, program_format=ProgramFormat.QIR_BASE_STRING)

# Submit the compiled QIR to the same device through QDMI.
job = device.submit_job(compiled.payload, compiled.program_format, shots)
job.wait()
counts = job.get_counts()

print(f"counts: {dict(sorted(counts.items()))}")
