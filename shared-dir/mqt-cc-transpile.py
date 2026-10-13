#!/usr/bin/env python3
"""Compile a Qiskit circuit with mqt-cc for a QDMI device model. Reads the
circuit as QPY from --input and writes the compiled circuit as QPY to
--output. Run with mqt-cc-venv's python -- the MLIR compiler bindings
(mqt.core.mlir) live only there."""

import argparse

from qiskit import qpy

from mqt.core.mlir import CompilerTarget, OutputFormat, QCProgram, compile_program
from mqt.core.qdmi.driver import open_device

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--input", required=True, help="path to the circuit to compile, as QPY")
parser.add_argument("--model", required=True, help="QDMI device model id, e.g. mqt.sc.iqm.garnet")
parser.add_argument("--qpy-version", type=int, default=qpy.QPY_VERSION,
                     help="QPY format version to write (match the reader's qiskit, default: this qiskit's own)")
parser.add_argument("--output", required=True, help="path to write the compiled circuit as QPY")
args = parser.parse_args()

with open(args.input, "rb") as f:
	circuit = qpy.load(f)[0]

# IQM hardware only runs its own native gate set (no h/cx); transpile with
# mqt-cc against the device model before handing the circuit to the shim.
# The compiler emits no QPY or OpenQASM 2 directly, so this round-trips its
# OpenQASM 3 output through QCProgram to get a Qiskit circuit back.
target = CompilerTarget.from_device(open_device(args.model))
qasm3 = compile_program(circuit, target=target, output=OutputFormat.OPENQASM3)
compiled = QCProgram.from_openqasm_str(qasm3.source).to_qiskit()
# The classical-register init in the OpenQASM 3 comes back as a store op,
# which backends do not run.
compiled.data = [inst for inst in compiled.data if inst.operation.name != "store"]

with open(args.output, "wb") as f:
	qpy.dump(compiled, f, version=args.qpy_version)

print(f"mqt-cc transpiled for {args.model}: {dict(compiled.count_ops())}")
