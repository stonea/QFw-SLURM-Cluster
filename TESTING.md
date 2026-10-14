# Testing the QRMI/QDMI shim and `mqt-cc`

This describes how to validate the QFw QRMI/QDMI front-end
(`services/svc_lib_qpm`) and the MQT Compiler Collection (`mqt-cc`) in the
containerized Slurm cluster. The shim has three test tiers:

1. **Local smoke:** routing and `qhw` normalization, with no credentials and no
   network access. This is the everyday check.
2. **Hardware introspection:** real device introspection through both QDMI and
   QRMI against an IQM system, confirming they return the same `qhw` shape.
   Requires IQM credentials.
3. **Through the site service plane:** a circuit run the way a user runs one,
   through a reservation to an administrator-started QPM service. The only tier
   that exercises the service path, where configuration is the sole input
   because no environment survives the hop.

Tiers 1 and 2 share one vehicle, `shared-dir/shim-smoke.sbatch`. It needs no
Slurm allocation and reads no Slurm environment, so both run it directly inside
`slurmctld`. Tier 3 is a different setup in every respect and is described
separately below.

## Build the cluster

```bash
./do_configure.sh --qfw-ref v0.1.0-rc.1 --qfw-slurm-ref v0.1.0-rc.1
./do_build.sh
./do_startup.sh
```

Omit the two ref options to build from `main`. Along with Slurm and the
simulators, the image installs QFw at `/opt/openqse/qfw`, and its Python
environment at `/opt/openqse/qfw-venv`, including the shim's QRMI and QDMI
dependencies.

## Which shim installation is tested

The image sets `QFW_PREFIX` and `QFW_VENV` to those paths, and
`shim-smoke.sbatch` honours both. So **by default the smoke tests the image
installation**, not a checkout of your own.

To test shim changes that are not in the image yet, build a developer override
and point the run at it, as described next.

## Optional: a developer override

Clone QFw onto the shared mount and build it inside the running cluster:

```bash
git clone --recursive https://github.com/openQSE/QFw.git shared-dir/QFw
./do_qfw_build.sh
```

`--recursive` is required, because the shim needs DEFw and the `qhw-*` packages.
The override has no venv of its own: it runs on the image's
`/opt/openqse/qfw-venv`, so a change that needs a new Python dependency, or a
different MQT Core, goes into the `Dockerfile` and a rebuilt image.
QFw declares its submodules over SSH, so without GitHub SSH access to openQSE,
rewrite them to HTTPS before cloning:

```bash
git config --global url."https://github.com/".insteadOf "git@github.com:"
```

The override installs a copy of the sources into `shared-dir/qfw-install`, so
editing `shared-dir/QFw/services/svc_lib_qpm` changes nothing until you
reinstall:

```bash
./do_qfw_build.sh
```

## Tier 1: local smoke (no credentials)

The smoke test resolves a device descriptor for `ornl-iqm-20q` from a
device-access file. That file is gitignored and the install tree ships no
default, so copy the example once:

```bash
cp shared-dir/iqm-device-access.yaml.example shared-dir/iqm-device-access.yaml
```

Leave the contents as they are. Tier 1 reads only the descriptor fields
(`provider`, `provider-device-id`, `libraries`, `preference`, `caps`), so the
`url` and `credential-db` values in the example are never dereferenced. Without
the file the run fails with:

```text
QFw device access config file was not found: ...
```

This file is separate from `/etc/openqse/qfw/device/device-access.yaml`, which
the cluster's site QPM services read. The smoke runs in-process and does not use
those services.

With the cluster running, test the image installation:

```bash
docker exec -w /workspace/qfw-container-base slurmctld \
  bash shim-smoke.sbatch 2>&1 | tee shared-dir/shim-smoke.out
```

or a developer override:

```bash
docker exec -w /workspace/qfw-container-base \
  -e QFW_PREFIX=/workspace/qfw-container-base/qfw-install \
  slurmctld bash shim-smoke.sbatch 2>&1 | tee shared-dir/shim-smoke.out
```

Submitting the script with `sbatch` also works on a cluster that defines the
`quantum` partition and `qpu` GRES its `#SBATCH` lines request. Neither tier
needs an allocation, so running it directly avoids depending on that
configuration.

Keeping a baseline to diff against is the usual way to check that an upgrade
changed nothing:

```bash
cp shared-dir/shim-smoke.out shared-dir/shim-smoke-baseline.out
```

Both files match the gitignored `shared-dir/*.out`, so they stay local.

Expected (abridged):

```text
[shim-smoke] imported frontend + drivers + descriptor + QRC: OK
[shim-smoke] [iqm-q20]  get_device_info            -> qdmi
[shim-smoke] [iqm-q20]  run_circuit                -> qrmi
[shim-smoke] [ibm-heron] introspection (device_info/coupling) -> qrmi (QRMI-only resource still introspects)
[shim-smoke] [ibm-heron] get_calibration_snapshot -> NOT_IMPLEMENTED (gap map: no calibration-capable library wired)
[shim-smoke] QRC constructed from descriptor:          OK
[shim-smoke] FoMaC Device -> qhw normalization: device(3 qubits ['QB1', 'QB2', 'QB3']) + coupling(2 edges, 2 ops), schema-valid
[shim-smoke] live introspection: skipped (set QFW_QC_URL + QFW_API_KEY to enable)

SHIM BIFURCATION + INTROSPECTION SMOKE: PASS
```

This exercises descriptor-driven routing, where introspection is composable with
QDMI preferred and execution is pinned to QRMI, the gap map, and the FoMaC to
`qhw` normalizer with real `jsonschema` validation, all without touching
hardware.

## Tier 2: hardware introspection (IQM credentials)

Tier 2 is the same run with credentials, which enables the live section. It
introspects the device through both QDMI and QRMI and compares the results.

For getting a token and for remote access over an SSH tunnel, see sections 1
and 3 of [IQM-ACCESS.md](IQM-ACCESS.md).

The live section runs only when **both** `QFW_QC_URL` and `QFW_API_KEY` are set
in the environment. A credential file on its own is not enough: the drivers
could use it, but the script skips the live section without both variables.

The shim takes the device alias from `provider-device-id` in
`shared-dir/iqm-device-access.yaml`. It does not read `QFW_IQM_QUANTUM_COMPUTER`,
so to target a different device, change `provider-device-id`.

```bash
docker exec -w /workspace/qfw-container-base \
  -e QFW_QC_URL="https://qccsw.ccs.ornl.gov" \
  -e QFW_API_KEY="<token>" \
  slurmctld bash shim-smoke.sbatch 2>&1 | tee shared-dir/shim-smoke.out
```

Add the `QFW_PREFIX` option from Tier 1 to test a developer override instead.

Expected additional lines, replacing the `skipped` line:

```text
[shim-smoke] live qdmi -> qhw-device-v1 (N qubits) + qhw-coupling-v1 (M edges)
[shim-smoke] live qrmi -> qhw-device-v1 (N qubits) + qhw-coupling-v1 (M edges)
[shim-smoke] cross-library: QDMI and QRMI agree on qhw shape (N qubits, M edges)
```

The `cross-library: ... agree` line is the key result. Introspection returns one
normalized shape regardless of which library served it. Check that `N` and `M`
match the device's known topology.

### When the QRMI leg reports unavailable

The shim fills QRMI's IQM endpoint and token variables from the same credentials
as the QDMI leg, so no Slurm reservation is needed, and this image does not load
the `spank_qrmi` plugin. If QRMI still fails, the leg prints:

```text
[shim-smoke] live QRMI introspection: unavailable (...) -- needs QRMI resource env (SPANK reservation)
```

That wording predates the shim supplying the environment itself. Treat it as a
QRMI failure and read the exception name in the parentheses. The run still
passes on the QDMI leg.

## Tier 3: through the site service plane

Tiers 1 and 2 import the front-end and call it in the same process. Tier 3 runs
a circuit the way a user does, through a reservation to a QPM service the
administrator started with `qfw-site-services`. It is the only tier that
exercises the service path, and it is worth running before trusting a shim
change in a real deployment, because a site service reads none of the
environment the first two tiers rely on.

That is the thing to understand before starting. Nothing a user or a job
exports reaches a site service, so `QFW_QC_URL`, `QFW_API_KEY` and the
`QFW_IBM_*` variables all stop working here. Configuration is the only input.
A device that works in tier 1 through environment variables alone will fail in
tier 3 until the same values are in the device entry.

Three things point somewhere other than where the first two tiers put them, and
each one fails quietly by testing something other than what you meant.

**The installation.** `qfw-site-services` defaults to `/opt/openqse/qfw` and
`/opt/openqse/qfw-venv`, the image-baked QFw, so by default tier 3 tests the
image and not your override, however recently you ran `do_qfw_build.sh`.

It names the prefix differently from the smoke, which is worth knowing before
you set anything. The smoke reads `QFW_PREFIX`; `qfw-site-services` reads
`QFW_INSTALL_PREFIX` and does not look at `QFW_PREFIX` at all. Both read
`QFW_VENV`, and both default it to the image's `/opt/openqse/qfw-venv`, which
the override also runs on. So exporting `QFW_PREFIX` leaves the image's QFw
running. Set the one it actually reads:

```bash
docker exec \
  -e QFW_INSTALL_PREFIX=/workspace/qfw-container-base/qfw-install \
  slurmctld /bin/bash -lc 'qfw-site-services restart --target all'
```

`qfw-site-services` forwards it over SSH to each node, and the shared mount is
present on all of them, so the override resolves everywhere.

**The device configuration.** Site services read
`/etc/openqse/qfw/device/device-access.yaml`, provisioned from
`config/device-access.yaml` by `do_startup.sh`. They do not read
`shared-dir/iqm-device-access.yaml`, which reaches the smoke only because
`shim-smoke.sbatch` sets `QFW_DEVICE_ACCESS_CFG`. A device you added for tier 1
is simply absent here.

**The credentials.** Site credentials come from
`/etc/openqse/qfw/device/qpu-users.json`, resolved relative to the device
configuration through each device's `credential-db` key. The per-device entry
key is `api_key`; `token` is accepted in a reservation credential but not in
this database, so spelling it `token` reads as no credential at all. Both the
user record and the device record also need `"enabled": true`.

To test a device of your own, edit an existing entry in place rather than
adding one, keeping its key so
`/etc/openqse/qfw/services/site-services.yaml` still names a device that
exists. Each service's node is what matters: `shim-ibm-156-nh` runs on
`ibm-156-nh`, so that container is the one whose configuration it reads.

Then drive it through a reservation rather than by calling the front-end. The
examples install alongside the QFw they came from, under
`<prefix>/share/qfw/examples`, which `qfw-activate` exports as
`QFW_SHARE_DIR`. Reaching them through that variable rather than a literal path
keeps the example and the installation you are testing in step:

```bash
docker exec slurmctld /bin/bash -lc \
  'source /opt/openqse/qfw/bin/qfw-activate --venv /opt/openqse/qfw-venv \
   && "${QFW_SHARE_DIR}/examples/qfw_ghz.sh"'
```

Substitute your override's prefix and venv to run its copy instead.
`qfw_ghz.sh` is the pattern to copy, through
`qfw_example_srun_with_backend_reservation`. The shim services declare
`credential-mode: required`, so they expect a credential to arrive with the
reservation.

Two things to know when it goes wrong. `qfw-site-services status` distinguishes
the two failures: `DOWN` means the service is not running, while `UNKNOWN`
means its status could not be read at all, so something went wrong before the
service was ever reached. `UNKNOWN` is the case that carries a reason, and
`--json` returns the captured output as each service's `detail.output`, which
is where to look first. And edits under `/etc/openqse/qfw/` live in the
container, so
they are lost when containers are recreated. `provision-qfw-cluster.sh`
installs those files only when they do not already exist, so to make a change
durable, edit `config/` on the host and delete the installed copy so the next
`do_startup.sh` re-provisions it.

## `mqt-cc` smoke test (no credentials)

The image builds MQT Core from the ref selected by `do_configure.sh` and installs
it with Qiskit at `/opt/openqse/mqt-cc-venv`. This separate
environment allows the compiler and QFw to use different Qiskit versions.
It is the only mqt-cc environment; to try another MQT Core ref, select it with
`do_configure.sh --mqt-core-ref` and rebuild the image.

`shared-dir/mqt-cc-smoke-test.sbatch` compiles a Qiskit circuit for
MQT Core's bundled IQM Garnet model to QIR Base. It uses QDMI to read the
model's capabilities and run the QIR on local DDSIM. The model is a
historical hardware snapshot, not live device discovery. This check makes no hardware calls and does not exercise
QFw submission or QRMI. The image build runs it too.

Test the image installation:

```bash
docker exec -w /workspace/qfw-container-base slurmctld \
  bash mqt-cc-smoke-test.sbatch 2>&1 | tee shared-dir/mqt-cc-smoke-test.out
```

To test on a Slurm application node, submit from inside `slurmctld`:

```bash
cd /workspace/qfw-container-base
sbatch --wait mqt-cc-smoke-test.sbatch
```

The job uses the `normal` partition and needs no QPU allocation. Success ends
with `MQT-CC QIR SMOKE TEST: PASS`.

## IBM Quantum System API simulator (no credentials)

`docker-compose.ibmsim.yml` adds the simulator from
[qrmi-community/simulated_quantum_resource](https://github.com/qrmi-community/simulated_quantum_resource):
IBM's Quantum System REST API with Qiskit Aer and the `qiskit-ibm-runtime`
fake backends behind it, plus the S3-compatible store (RustFS) that QRMI stages
job input and results through. Two clients reach it, over two IBM APIs:

- QRMI's `IBMQuantumSystem` resource, unchanged from what reaches a real IBM
  system; only the addresses differ. It is the same client the shim's IBM
  execution path (`QrmiDriver._run_ibm_circuit`) drives, so the simulator also
  lets that path run without an IBM account.
- MQSC's IBM QDMI device library
  ([ibm-qdmi-device](https://github.com/munich-quantum-software/ibm-qdmi-device),
  the `ibm-qdmi` package in the qfw venv), opened through MQT Core's QDMI
  driver like the IQM and Braket libraries. It speaks IBM Quantum Platform's
  Qiskit Runtime REST API, not the Quantum System API, so the overlay also runs
  `ibmsim-runtime` (`ibmsim-runtime/app.py`): a front that takes Runtime-shaped
  requests (parameters inline, results from `GET /v1/jobs/{id}/results`),
  stages each job's input and results in the S3 store itself and submits it to
  the simulator in Quantum System shape. The simulator stays the execution
  engine.

Start it beside the running cluster (the first `up` builds the simulator and
Runtime-front images; the simulator's ref is pinned in `ibmsim/Dockerfile`):

```bash
./do_ibmsim.sh up
```

or configure it in so `do_startup.sh` starts it with the cluster:

```bash
./do_configure.sh --ibmsim ...
```

The four containers (`ibmsim`, `ibmsim-s3`, `ibmsim-s3-init`, `ibmsim-runtime`)
join the cluster network and are not Slurm nodes. No cluster container needs
recreating: the API key, service CRN and S3 key pair are placeholders shared by
the overlay and the tests, and the tests default to the in-network addresses.
The CRN placeholder has the shape of a real instance CRN because the QDMI
device library validates it before sending anything.

### Through QRMI: `ibm-qrmi-qktr.sbatch`

`shared-dir/ibm-qrmi-qktr.sbatch` runs a 3-qubit GHZ circuit through QRMI
directly, without the shim: it points QRMI's `{backend}_QRMI_IBM_QS_*` settings
(and `{backend}_QRMI_JOB_TIMEOUT_SECONDS`) at the simulator and its S3 store,
opens a `QuantumResource` of type `IBMQuantumSystem`, transpiles against the
`Target` from QRMI's `get_backend()` (the simulator's configuration and
properties) and runs it with QRMI's `SamplerV2`, which stages the job through
S3 and deletes it when its results are in. Submit from inside `slurmctld`:

```bash
docker exec -w /workspace/qfw-container-base slurmctld \
  bash /mnt/sbatch_poll_wait.sh /mnt/ibm-qrmi-qktr.sbatch
```

By default it tests the image installation; add
`-e QFW_PREFIX=/workspace/qfw-container-base/qfw-install` to test the
developer override. `QFW_QPU_DEVICE_ALIAS` selects the simulated backend
(`fake_lagos` by default; `fake_cairo`, `fake_brisbane`, `fake_torino`). Pass
such settings through the environment, as `docker exec -e` does; on this
cluster `sbatch --export=ALL,VAR=...` makes slurmd fetch the login environment
with `su`, which fails and takes the node down.

Expected (abridged; the noise model is the fake backend's, so FakeLagos leaves
about 70% of the shots in the GHZ states and FakeBrisbane about 95%):

```text
device: fake_lagos (7 qubits)
counts: {'000': 370, '001': 20, '010': 57, '011': 78, '100': 70, '101': 57, '110': 24, '111': 348}
```

`000` and `111` should dominate. If the stack is down the job fails at once with
`No IBM Quantum System API simulator at http://ibmsim:8290`. The simulator's
Swagger UI is at `http://localhost:8290/docs` and `./do_ibmsim.sh logs` follows
its log, where every job's presigned S3 URLs and Aer output appear.
`./do_ibmsim.sh purge` also removes the S3 volume.

### Through QDMI: `ibm-qdmi-qktr.sbatch`

`shared-dir/ibm-qdmi-qktr.sbatch` runs the same GHZ circuit on the same
simulator over QDMI, the way `iqm-qdmi-qktr.py` reaches IQM: it registers the IBM
device library under the ID its package publishes and opens it as MQT Core's
Qiskit `QDMIBackend`, with the API key as the token, the backend as `custom1`,
the CRN as `custom2` and both URLs pointed at the Runtime front. The backend's
`Target` carries what the session reports (operations with their loci,
fidelities and durations); the circuit is transpiled against it and run through
the backend's sampler, which submits OpenQASM 3 over QDMI. The OpenQASM 3
export is `ibm.qdmi`'s, since the simulator's importer rejects the classical-bit
initialization MQT Core's default serializer emits. (`ibm.qdmi.qiskit.IBMBackend`
would do both, but in ibm-qdmi 0.1.1 it fails building its `Target` because the
device library does not report a parameter count for parameterless gates.) It
does not go through the shim; `ibm-shim-qktr.sbatch` runs the same leg through
the shim's `QdmiDriver`.

The device library allows plain HTTP only to loopback addresses and verifies
every HTTPS peer, so `ibmsim-runtime` serves HTTPS. At each start it creates
a private CA, signs a certificate for `ibmsim-runtime`, `localhost` and
`127.0.0.1` with it, discards the CA key and publishes the CA certificate to
`shared-dir/ibmsim-tls/ca.crt` (`/mnt/ibmsim-tls/ca.crt` in the cluster;
`ibmsim-runtime/tls.sh`). The job points `CURL_CA_BUNDLE`, which the device
library reads for its trust store, at that file and connects to
`https://ibmsim-runtime:8291` directly. Submit the same way, with the same
environment settings:

```bash
docker exec -w /workspace/qfw-container-base slurmctld \
  bash /mnt/sbatch_poll_wait.sh /mnt/ibm-qdmi-qktr.sbatch
```

The image installs `ibm-qdmi` into its qfw venv; an image built before it was
added needs rebuilding with `./do_build.sh`, and the job says so if it is
missing. Expected:

```text
device: fake_lagos (7 qubits)
counts: {'000': 371, '001': 16, '010': 53, '011': 85, '100': 64, '101': 58, '110': 18, '111': 359}
```

`000` and `111` should dominate. The physical qubits matter: FakeLagos's
qubit 2 reads out wrongly 46% of the time. The `Target` carries QDMI's per-site
measurement fidelity, which steers the transpiler to physical qubits
`[3, 1, 0]` instead. If the stack is down the job fails at once with
`No Runtime front for the IBM simulator at https://ibmsim-runtime:8291`, or,
if the front has never started, with `No CA certificate at
/mnt/ibmsim-tls/ca.crt`. The front's Swagger UI is at
`https://localhost:8291/docs` (trust `shared-dir/ibmsim-tls/ca.crt`, or accept
the browser's warning; `curl --cacert shared-dir/ibmsim-tls/ca.crt
https://localhost:8291/version` from the host), and its log (in
`./do_ibmsim.sh logs`) shows every Runtime request and the simulator job id it
became.

### Through the shim: `ibm-shim-qktr.sbatch`

`shared-dir/ibm-shim-qktr.sbatch` runs the GHZ circuit through QFw's QRMI/QDMI
shim (`services/svc_lib_qpm`) as a Python module, the IBM counterpart of
`iqm-shim-qktr.sbatch`. It transpiles with Qiskit's `transpile()` against the
IBM QDMI device as MQT Core's `QDMIBackend`, sends the circuit as QPY, and
routes `run_circuit` to either library: `SHIM_TEST_LIB=qrmi` uses
`QrmiDriver`'s IBM path (QRMI's `IBMQuantumSystem` against the simulator and
its S3 store), and `SHIM_TEST_LIB=qdmi` uses `QdmiDriver`'s IBM profile
(`IbmQdmiProfile` in `drivers/qdmi_profiles.py`: the ibm-qdmi device library
against the Runtime front, OpenQASM 3). Both drivers see the circuit is
already native and keep its layout. Unset, the descriptor's execution owner
(QRMI) runs it. The synthetic descriptor carries both legs' settings: the
Quantum System API, IAM and S3 for QRMI, and `runtime_endpoint` and
`runtime_auth_url` (the `runtime-endpoint` and `runtime-auth-url`
device-access keys) for QDMI, which unset leave the library on IBM Cloud.

```bash
docker exec -e SHIM_TEST_LIB=qrmi -w /workspace/qfw-container-base slurmctld \
  bash /mnt/sbatch_poll_wait.sh /mnt/ibm-shim-qktr.sbatch
docker exec -e SHIM_TEST_LIB=qdmi -w /workspace/qfw-container-base slurmctld \
  bash /mnt/sbatch_poll_wait.sh /mnt/ibm-shim-qktr.sbatch
```

The IBM profile needs a QFw with the IBM profile in `qdmi_profiles.py` and
`ibm-qdmi` in the venv. The image's venv has `ibm-qdmi`, but until the profile
reaches QFw's `main` the image's `/opt/openqse/qfw` install, which the login
environment's `QFW_PREFIX` points at, lacks it, so the job falls back to the
developer install under `QFW_BASE` on the image's venv when that has it, and
says so. Expected
(FakeCairo):

```text
device: ibm-qsa-sim (ibm:fake_cairo)
routing run_circuit -> qdmi
circuit format: qpy+gzip
counts: {'000': 469, '001': 10, '010': 4, '011': 16, '100': 11, '101': 7, '110': 7, '111': 500}
```

The simulator counts every job it still holds against a backend's five
execution lanes, finished or not, and answers 429 beyond that. The QRMI route
deletes each job once its results are in. A Runtime client never deletes its
jobs, so `ibmsim-runtime` deletes a job upstream as soon as it sees it end
and keeps its final record to keep answering for it, the way Runtime frees a
lane when a job ends.

## What to capture

The full `shim-smoke.out`, in particular the qubit and edge counts from each
leg, whether the QRMI leg ran or reported unavailable, and whether the
`cross-library: ... agree` line appeared.

For the `mqt-cc` smoke test, capture `mqt-cc-smoke-test.out` or the Slurm job's
`mqt-cc-smoke-test.<job-id>.out`.

For the IBM simulator tests, capture the job's `slurm-<job-id>.out`: the backend
alias and qubit count, the counts line and the `GHZ fidelity proxy` line, and
for the QDMI test the physical qubits the transpiler chose.
