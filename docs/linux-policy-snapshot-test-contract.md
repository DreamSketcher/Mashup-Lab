# Linux trusted policy snapshot — implementation and test contract

> **Scope update:** This document is optional trusted-execution research, not a
> prerequisite for the Mashup Lab music MVP. For current priorities and the
> simpler render-time binding direction, see [MVP scope](mvp-scope.md). Historical
> references to “MVP” below apply only to the proposed trust subsystem.

Status: **experimental scaffold, not implemented or supported**. The current
`mashup.linux_policy_snapshot.capture_policy_snapshot()` always returns
`UNAVAILABLE`, performs no filesystem access, produces no bytes and does not
check policy authority, take locks or authorize planner execution. It is not
connected to `compare-policy` or another CLI. Scaffold unit tests check only
these fail-closed properties; they are not Linux security tests.

The governing design is [Trusted Policy Loading](trusted-policy-loading-specification.md).
This document sets acceptance criteria, not a claim that a platform or mechanism
has been selected and proven secure. No Linux kernel, filesystem, runtime,
container environment or privilege model is currently approved.

## Staged delivery

1. **Trusted snapshot:** obtain path only from a protected installation; securely
   resolve it, inspect path/file authority and mounts, read bounded exact bytes,
   protect their storage, and hash and parse the *same* bytes. A successful
   snapshot would establish only its documented filesystem/trust properties,
   not authorization to execute. The snapshot stage is not complete if any
   required ownership, ACL, mount or filesystem check is unavailable.
2. **Update coordination:** implement trusted updater and stable shared lock,
   timed waits, crash/recovery semantics and holding the lock through the
   separately defined admission point. No admission or revocation-order guarantee
   may be advertised from stage 1 alone. This stage is not implemented.

Any future PASS must identify the checks performed and the supported environment;
a failed check is FAIL, and an inability to establish a required property is
UNAVAILABLE. Both deny. NOT_RUN is not PASS. Do not silently fall back to
`compare-policy`, an unprotected path, earlier snapshot, or mode-bit-only checks.

## Design obligations before implementation

A concrete adapter must specify and test, for its exact supported Linux profile:

- trusted installation and configuration provenance; root of resolution,
  descriptor-based safe path resolution, directory and file ownership/modes,
  ACLs (including inherited/default ACL effects), hard links, capabilities and
  prevention of untrusted replacement or in-place writes;
- allowed filesystem/mount types, relevant kernel and filesystem versions,
  mount namespace and topology verification from path resolution through use,
  and handling topology changes or inspection that is incomplete/unavailable;
- bounded read and protected snapshot mechanism, lifetime and cleanup; hash and
  parser must operate on the exact same immutable bytes that consumers receive.
  A descriptor, file hash, `stat`, or private filename alone does not guarantee
  immutability or trusted installation;
- updater/loader shared lock identity, ownership, safe creation, lock timeouts,
  crash recovery and publication durability; ordering relative to the admission
  point must follow the governing contract. Privileged non-cooperating writers
  and compromised kernels remain outside the stated threat model;
- explicit resource limits and failure diagnostics; cleanup on all error paths,
  including uncertain outcomes. No snapshot result is a planner admission.

If a property cannot be verified on a configuration, reject or report
UNAVAILABLE. For example, do not assume mode bits capture ACL effects, and do
not assume observing mount topology once makes it immutable. Define how an
attacker's race is actually prevented or detected; repeated metadata checks
alone do not eliminate TOCTOU.

## Independent platform acceptance matrix

Unit tests with mocks are useful for error paths but cannot prove Linux access
control. The following require real integration tests in a controlled,
appropriately privileged environment; distinguish tests skipped for missing
capability from tests that passed. Each run records exact kernel, distribution,
filesystem and mount options, ACL support, namespace configuration, runtime and
privilege assumptions. Results apply only to the tested and documented support
matrix, not every Linux system.

| Area | Required cases and observations |
| --- | --- |
| Authority and paths | Trusted path succeeds only once implemented. Reject/unavailable for untrusted owners, writable ancestors/files, unexpected ACL grants and inherited/default ACL effects; reject symlinks at final and intermediate components, non-regular files, malicious hard links and unsafe path swaps. |
| Mounts and namespace | Exercise bind mounts, mount namespaces, unsupported filesystems and mount-topology changes during resolution/read. Prove enforcement or fail closed when facts cannot be checked. |
| Snapshot bytes | Oversize and malformed input fail; test file replacement and in-place modification concurrently with capture. Compare recorded hash and parsed content to the exact protected snapshot bytes consumed, not a later reread by path. |
| Lock identity | Attempt lock-file replacement and separate-lock races; verify a single protected lock serializes all cooperating actors and cannot be redirected by untrusted users. |
| Update ordering | Real concurrent updater and admission attempts: completed revocation before the documented admission point denies; admission before completed revocation follows the documented in-flight rule. Snapshot-only functionality must not claim either outcome before this layer exists. |
| Timeout and failure | A held lock or hung updater produces a documented bounded timeout and fail-closed result. Unavailable ACL, mount, locking or integrity evidence must be UNAVAILABLE, not PASS. |
| Crash recovery | Terminate actors at every critical lock, write, sync, rename, decision-record and release point. Check consistent recovery, no partial policy trusted and no unauthorized planner release. Verify behavior when completion is unknown. |
| Boundary | No snapshot check is reported as an execution ADMIT; `compare-policy` retains `trust: not_checked` and `execution: not_checked`. No audio or container execution is introduced by the snapshot tests. |

A test matrix and concrete runtime mechanism are prerequisites for claiming even
one supported configuration. Security against compromised root, kernel or
runtime is not claimed. No tests for stages 1 or 2 are currently implemented.
