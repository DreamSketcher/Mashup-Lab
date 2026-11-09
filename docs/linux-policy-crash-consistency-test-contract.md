# Linux policy publication: crash-consistency test contract — draft v0.1

Status: **test design, not implemented or verified**. There is no production
policy updater, trusted snapshot loader, recovery gate or admission mechanism.
The current `capture_policy_snapshot()` remains `UNAVAILABLE`. This document
specifies a candidate experiment and its acceptance criteria; it does not claim
that a filesystem, VM, host or device already meets them. See the
[trusted policy contract](trusted-policy-loading-specification.md),
[Linux profile research](linux-policy-snapshot-platform-research.md), and
[platform test contract](linux-policy-snapshot-test-contract.md).

## Goal and scope

After interruption of a single policy publication, determine what bytes can be
observed at the policy pathname after recovery and whether a future loader may
safely proceed. Never accept a partially written, corrupt, malformed, or
untrusted policy. **Complete bytes are necessary, not sufficient for trust**:
the installation authority, filesystem/path checks, policy schema and admission
contract still apply. Outcomes depend on the tested filesystem, kernel,
virtualization, storage, cache/flush behavior and fault mechanism.

The existing GitHub runner test kills an updater before/after rename. It is a
process-exit observation only; it does not test `fsync` of the parent directory,
reboot, power loss, recovery or the candidate kernel. It is not evidence of
crash consistency for this contract.

## Candidate protocol and fixtures

Tests run only on an independently verified **disposable** target VM matching
the candidate profile, with a dedicated local ext4 filesystem and protected
test directory, a stable pre-created lock inode, a trusted cooperating updater,
and separate reader and unprivileged adversarial identities. Do not operate on
production policy or lock paths. Capture the exact OS/kernel/package, filesystem
features and mount options, virtual disk format, host hypervisor, cache mode,
flush/barrier behavior, ACLs, namespace, privileges, image hashes and recovery
steps. Where any prerequisite or the specific fault mechanism is unknown or
unavailable, mark the affected case UNAVAILABLE. The exact VM image and storage
configuration are not yet pinned.

Create two **independently validated** policy files `old` and `new` with distinct
known exact bytes and SHA-256, both within size limits, structurally valid and
installed by a trusted test setup. `old` starts as the live policy; record its
bytes and digest and establish it as durable before beginning each trial. Define
and test durability of this baseline separately. Use different approval contents
(e.g. active versus revoked) so rollback is observable; never use real trust
entries. Each trial starts from a fresh reset fixture. The temporary file is
newly created in the same protected directory and filesystem as the policy;
its name must be unique and must not alias the live policy or lock file.

Candidate updater, holding the exclusive protected coordination lock throughout:

1. Create the new temporary regular file with safe flags and restrictive
   ownership, mode and ACL; write the complete `new` bytes, handling partial
   writes and errors, and validate the file and its exact bytes.
2. `fsync` the temporary file and confirm successful return.
3. Atomically rename it over the policy path on the same filesystem; confirm
   successful return. The lock file is **not** renamed, deleted or recreated.
4. `fsync` the parent directory and confirm successful return. Only then may
   the updater report publication completed. Release the lock after the declared
   publication/decision protocol finishes.

[`rename(2)`](https://man7.org/linux/man-pages/man2/rename.2.html) documents
pathname replacement, and [`fsync(2)`](https://man7.org/linux/man-pages/man2/fsync.2.html)
notes that syncing a file alone does not necessarily persist its directory
entry. These interfaces do not alone prove persistence on an arbitrary VM or
storage stack. This document does not define a production implementation.

## Fault points and acceptable recovered bytes

Fault hooks must be externally observable and synchronized at the stated points;
record actual syscall return codes. An uncertain boundary is not counted as a
case at either side of that boundary. After recovery, compare the policy bytes
**exactly** to independently retained old/new fixture bytes, then parse the
same captured bytes. A missing policy, third value, truncation, mixed bytes or
parse failure is FAIL, except that an unreadable or uninspectable recovery is
UNAVAILABLE. `old` and `new` must be distinguishable and neither is inferred
from the recovered file. Temporary-file presence is recorded separately; it
must never be treated as the live policy or auto-promoted without an explicit,
validated recovery protocol.

| ID | Verified interruption point | Acceptable recovered live-policy bytes | Additional condition |
| --- | --- | --- | --- |
| C0 | Before temp creation/write; old baseline durable | `old` only | No update has been published. |
| C1 | Temp created/written, before successful file `fsync` | `old` only | Temp may be absent or incomplete; it cannot be promoted. |
| C2 | File `fsync` succeeded, before `rename` | `old` only | Temp may exist; the live path has not been replaced. |
| C3 | `rename` succeeded, before successful parent-directory `fsync` | `old` **or** `new`, both exact and valid | After a reboot/power-loss-like fault, durable outcome is not established. Do not treat either as proof that a reported update completed. |
| C4 | Parent-directory `fsync` succeeded | `new` only | Conditional on a storage stack that correctly honors acknowledged flushes; if that condition cannot be established or tested, do not claim durability. |

This table is an **acceptance target** for the stated fixture and protocol, not
a universal ext4 theorem. A fault may occur between individual write calls, not
just after writing all bytes: include controlled partial-write subcases for C1.
For C3, process-only `SIGKILL` normally leaves the kernel and page cache alive;
observing `new` there does not prove which bytes survive a subsequent power
fault. For C4, success of a syscall is a protocol boundary, not independent
proof that every real device honors flushes.

## Distinct failure classes

Run and report each class independently. Do not infer one result from another.

- **Process termination:** deliver `SIGKILL` to the updater at each synchronized
  fault point while the VM/kernel remain running. Record PID, signal and exit
  status, verify no unexpected inherited lock descriptor keeps the lock, and
  observe what a subsequent cooperating reader actually sees. This tests neither
  reboot nor physical power failure. Crash recovery must never equate lock
  release with publication success.
- **Abrupt VM termination/reset:** an external controller stops or resets the VM
  at each point without a guest shutdown. Record whether the method is a QEMU
  reset, process kill, hypervisor power-off or another exact mechanism, including
  host page cache and virtual disk cache mode. Restart the same disk and inspect
  after normal ext4 recovery. A reset can leave host caches intact and is not
  necessarily equivalent to loss of power.
- **Power-loss simulation:** use a documented, independently verified mechanism
  capable of discarding or controlling unflushed writes at the appropriate layer;
  record exactly which guest, hypervisor, host and storage caches it affects.
  If no such mechanism is available, mark this class UNAVAILABLE. Neither a
  process kill nor an ordinary VM reset is automatically a power-loss test.
  Even a valid simulation does not prove physical hardware behavior beyond its
  stated model.

All destructive actions target only the disposable VM/test filesystem. A harness
must not initiate host power/reset operations from a production or shared system.
Record unexpected auto-repair/fsck results and never label an uninspectable
filesystem PASS. No such VM or fault controller is currently available here.

## Recovery, rollback and admission

After a crash, obtain the protected lock using the verified coordination
protocol and read a new stable snapshot; do not assume that an unlocked inode
means a previous update completed. Validate directory/file authority, exact
snapshot bytes, schema and the recovery state before any future admission.
Retained temporary files are not policy and cannot silently become policy.

An `old` policy after C3 may be an allowed filesystem outcome, but it may roll
back a revocation. **Allowed bytes are not permission to admit a planner.** If a
revocation was reported complete, a stale `old` version must not be silently
used. The system needs a trusted, durable completion/decision record or another
specified anti-rollback and recovery protocol that establishes which state was
acknowledged. That record's ordering, atomicity, trust, recovery and failure
behavior are **not yet finalized or implemented**. The separate
[anti-rollback proposal](linux-policy-anti-rollback-specification.md) explores
an external durable authority, but does not select or implement a backend. If completion or ordering
cannot be established, the recovery gate and admission remain UNAVAILABLE and
fail closed. Lock coordination does not itself prevent rollback after reboot.

The proposed admission point in the trusted policy contract is a decision
recorded while holding the coordination lock after mandatory checks; no such gate
exists today. Tests of revocation relative to that point are NOT_RUN until the
actual updater, recovery and admission mechanisms and their interfaces exist.
A simulated in-memory decision is not an admission test. Do not assume that
`fsync(parent)` records an admission decision or vice versa.

## Matrix, evidence and verdicts

Each case is keyed by fixture/image ID, fault point C0–C4, failure class,
iteration and actor. Include partial-write subcases, syscall failures and
timeouts; run multiple independent repetitions on freshly prepared fixtures.
The harness must save raw hook events, times/ordering, syscall results, process
and VM exits, pre/post filesystem diagnostics, candidate version/hash,
recovered bytes/hashes and exact comparison results. Record the success/failure
of file and directory fsync, the observed lock state and recovery decisions.
Evidence must be complete enough for an independent reviewer to identify the
actual fault point; insufficient evidence means UNAVAILABLE, not PASS.

- **PASS:** that specific implemented scenario ran on a recorded profile with
  all prerequisites established, its actual fault mechanism and boundary are
  independently confirmed, observed bytes match the table, and the specified
  recovery/admission behavior was verified. PASS applies only to that case and
  tested model, not to Linux generally. Until recovery/admission exists, an
  individual *filesystem observation* may be recorded but is not an end-to-end
  PASS for this contract.
- **FAIL:** an observed forbidden state or violation, e.g. partial live policy,
  acknowledged durable update rolling back under the tested assumptions,
  corrupt snapshot, or admission while recovery is unresolved.
- **UNAVAILABLE:** required VM, storage/fault mechanism, evidence, privilege,
  recovery procedure or exact profile cannot be established. Infrastructure
  failure is not evidence of a safe outcome.
- **NOT_RUN:** case deliberately not attempted, including unimplemented updater,
  recovery or admission checks. It is not equivalent to PASS or FAIL.

A matrix or stress test cannot exhaust every possible filesystem/interleaving or
prove safety under a compromised privileged administrator, kernel, hypervisor
or storage device. Support requires reviewed mechanisms, concrete failure model,
repeatable independent evidence and explicit residual risk, not merely a green
CI job.
