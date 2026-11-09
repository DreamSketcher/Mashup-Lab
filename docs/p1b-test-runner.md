# P1-B test runner — experimental and incomplete

This is a **partial executable evidence harness**, not a complete trusted
snapshot acceptance suite. It does not change production code, create or approve
a VM, perform planner admission, or replace P1-A/P1-C/P1-D. The existing Linux
snapshot API always returns `UNAVAILABLE`.

The runner at `scripts/p1b/run.py` assigns stable IDs, prerequisites, expected
and actual results and PASS/FAIL/UNAVAILABLE/NOT_RUN statuses. P1B-01–05 invoke
existing independent Linux primitive probes (openat2, path race, ACL, memfd and
flock), each in a separate process with a 60-second timeout and per-probe raw
stdout/stderr. These tests use temporary subdirectories of an explicitly supplied
work directory. They are not tests of the snapshot implementation and cannot
prove its security. All P1B-06–18 are **NOT_RUN** until a trusted snapshot,
updater/admission implementation and independent adversarial fixtures/oracles
exist. The catalog identifies those missing scenarios; it is not an executable
implementation of those tests. Do not claim the requested complete P1-B
acceptance suite has been delivered.

The preflight gate checks only Ubuntu 24.04, x86-64, the running kernel and exact
installed kernel package. It is deliberately not a P1-A verification: ext4,
ACLs, permissions, namespace, image provenance and capabilities must be checked
separately. A primitive PASS is only its observed behavior, not platform support,
policy trust or permission to execute. Outcomes depend on finite race sampling
and particular environment; absent privileges or tools are UNAVAILABLE.

## Running after provisioning an isolated test VM

First establish P1-A using the [P1 report and collector](linux-policy-snapshot-p1-report.md)
and the [platform research](linux-policy-snapshot-platform-research.md). Prepare
an empty, disposable, operator-reviewed ext4 test directory and separate report
directory. Never use system or production directories; ACL and race probes
create, modify and delete test objects beneath the supplied directory. The ACL
probe may invoke `sudo -n` solely to run a test as existing UID 65534; it does
not create accounts or edit system directories. Never pass untrusted work paths
or run this on a shared host.

```sh
python3 scripts/p1b/run.py --workdir /verified/disposable/empty-test-dir \
  --output /separate/new-report-dir --ack-disposable
```

Replace both paths after verifying the VM and storage. The command requires an
existing empty work directory, a new separate report directory, and explicit
acknowledgement. It never provisions, formats, mounts or deletes the supplied
work directory. It runs no primitive probe if the narrow OS/kernel/package gate
or environment collector is unavailable. It collects raw environment/mountinfo
and a JSON report plus any probe logs. The gate is **not** a security boundary
and does not verify that the supplied workdir is a dedicated ext4 mount: that
is an operator prerequisite. Exit 1 means a probe FAIL; exit 2 means at least
one UNAVAILABLE/NOT_RUN; exit 0 would require every scenario PASS and is not
possible while adapter tests remain NOT_RUN. Setup/argument errors also exit 2;
check whether `report.json` exists to distinguish them.

## Current execution evidence

There is no candidate VM in the current sandbox. A safe preflight on the wrong
host was used only to exercise the harness's gate. All primitive probes were
UNAVAILABLE and all adapter scenarios NOT_RUN; no P1-B Linux experiments were
run. See [report.json](evidence/p1b-preflight-unavailable/report.json),
[stdout](evidence/p1b-preflight-unavailable/stdout.txt) and the environment
collector output there. This evidence is not VM acceptance. Obtaining a
reproducible VM and implementing the missing snapshot and admission fixtures
remain blockers.
