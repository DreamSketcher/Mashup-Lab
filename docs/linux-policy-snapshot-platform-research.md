# Linux trusted policy snapshot: platform research

Date: 2026-11-08. Status: **research proposal, no Linux support claim**. No
adapter is implemented, no trusted policy snapshot is produced, and the existing
API remains `UNAVAILABLE`. This document addresses snapshot acquisition and
updater coordination, not planner admission, OCI verification or audio execution.
A snapshot PASS would never by itself authorize a planner. See the existing
[policy loading contract](trusted-policy-loading-specification.md) and
[snapshot test contract](linux-policy-snapshot-test-contract.md).

## Evidence and limits

This is a literature-based design and an experiment plan, **not results of the
proposed Linux experiments**. Official Linux kernel/man-pages and POSIX ACL
documentation are linked below. This workspace was only inspected read-only:
Debian 12, x86-64, kernel `6.1.158+`, uid 1001; `stat -f /` reports
`ext2/ext3` (that label alone does not prove an ext4 mount). It is not the
candidate machine. No privileged ACL, mount, crash or race trials were run.
No source below proves the end-to-end safety of the proposed adapter.

## One exact test candidate

Provision a **disposable, isolated VM**, not production:

- Ubuntu Server **24.04 LTS**, amd64, systemd; Ubuntu GA kernel package
  `linux-image-6.8.0-31-generic` version `6.8.0-31.31`, booted as
  `6.8.0-31-generic`. This is a fixed historical test kernel, **not a
  recommendation to deploy an unpatched kernel**. Capture package hashes and
  image provenance before running. A later security update is a new test profile.
- One local ext4 root filesystem containing the whole protected policy path and
  lock path, no overlay, NFS, FUSE, idmapped mounts or bind mounts on that path.
  Desired effective root mount options: `rw,relatime` and ext4 superblock
  options `rw,errors=remount-ro`, with ACL support enabled. Record the actual
  complete `mountinfo`, `findmnt` options, superblock flags/features, device,
  `tune2fs` and tool versions; a difference from the fixture is not silently
  accepted. The exact mkfs feature set, VM image digest and block/storage model
  must be pinned when the fixture is provisioned; until then this is a target,
  not a reproducible installed image. Ext4's documented options are in the
  [kernel ext4 documentation](https://www.kernel.org/doc/html/v6.8/admin-guide/ext4.html).
- Initial user namespace; loader and updater are root-owned, operator-installed
  systemd services running with UID 0, in the **same initial mount namespace**
  (`PrivateMounts=no` and no other namespace-altering service settings). The
  VM is provisioned with mount propagation recursively private; verify actual
  state rather than relying on a unit-file setting. No containers or idmapped
  mounts in this baseline. Only trusted administrators may change mounts or
  installation state. Untrusted test users have no relevant capabilities
  (`CAP_SYS_ADMIN`, `CAP_DAC_OVERRIDE`, `CAP_DAC_READ_SEARCH`, `CAP_FOWNER`,
  `CAP_SYS_PTRACE`), no policy/lock write access and no ptrace access to the
  trusted processes. Verify effective, permitted, inheritable, ambient and
  bounding capability sets as appropriate. A malicious root, kernel, trusted
  service or storage administrator is outside the threat model.
- Proposed paths: `/etc/mashup-lab/policy.json` and a distinct, permanently
  provisioned `/etc/mashup-lab/policy.lock`; `/`, `/etc` and `/etc/mashup-lab`
  are root-owned and non-writable by group/other and untrusted principals.
  The lock inode is never replaced by either participant. No independent
  privileged process may change the tree outside the agreed protocol during an
  attempt. Baseline must explicitly inspect access/default ACLs and mount state.

The Ubuntu GA kernel family and exact package designation should be confirmed
from the archived distribution packages during provisioning; the
[Ubuntu release/kernel documentation](https://documentation.ubuntu.com/real-time/reference/releases/)
identifies the 24.04/6.8 family, not this VM's exact artifact. If the exact
package/image cannot be obtained and validated, the candidate is UNAVAILABLE;
do not substitute another kernel and call it this test. Profile restrictions
are intentionally tighter than a general Linux deployment.

## Path resolution and mount topology

**Candidate:** begin from a trusted root directory descriptor, use `openat2()`
with a relative path and `RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS |
RESOLVE_NO_MAGICLINKS | RESOLVE_NO_XDEV`, then inspect each relevant directory
and final object via stable descriptors. `RESOLVE_NO_SYMLINKS` covers all path
components (including magic links); `NO_MAGICLINKS` is explicit. `NO_XDEV`
rejects crossing mount points, including bind mounts, during resolution;
`BENEATH` rejects escapes and absolute paths. Do not silently retry with weaker
flags. The [openat2(2) manual](https://man7.org/linux/man-pages/man2/openat2.2.html)
documents flags and errors, including `ELOOP`, `EXDEV`, and `EAGAIN` for
uncertainty under `BENEATH`/`IN_ROOT`. Bound any `EAGAIN` retries; exhaustion or
unsupported syscall/flags means UNAVAILABLE. `OPENAT2_REGULAR` is a newer API,
not assumed available on this 6.8 profile: verify final file type by `fstat`.
Avoid opening an unverified device/FIFO in a way that blocks or causes side
effects; the exact safe final-object open/identity strategy is **open**.

A successful constrained lookup does not certify the starting root descriptor,
ownership, ACLs, absence of existing writers or mount history. Root descriptor
provenance is a bootstrap requirement. Do not use separate path-based `stat`
checks followed by another open as proof that the same directory chain was used.
Opening each component and then resolving descendants relative to it can pin
objects but does not alone prove that the final pathname is still attached to
the originally checked chain: trusted namespace and mutation exclusion matter.
Choose and test a strategy that binds checked directory identities to the file
actually consumed; if it cannot be demonstrated, UNAVAILABLE.

Inspect `/proc/self/mountinfo` and descriptor-based `statx` mount information;
record namespace identity and propagation. The kernel documents that mount IDs
may be reused after unmount, and `mountinfo` is a view of a mount namespace, not
a transaction or history ([kernel proc documentation](https://docs.kernel.org/filesystems/proc.html),
[statx(2)](https://man7.org/linux/man-pages/man2/statx.2.html),
[mount_namespaces(7)](https://man7.org/linux/man-pages/man7/mount_namespaces.7.html)).
Comparing `st_dev` alone does not detect all bind mounts. `NO_XDEV` prevents
crossing a mount at lookup, not replacement of the starting mount or mutation
later; two identical before/after snapshots cannot rule out an intervening
change. The baseline assumes an operator-controlled private namespace with no
untrusted mount authority; how to establish and maintain that assumption for a
real systemd service, including propagation and namespace membership, remains a
**release-blocking experiment/design question**. If topology cannot be safely
held/validated throughout the operation, UNAVAILABLE.

## Authority, ACL and concurrent writers

For each pinned ancestor and the final regular file, inspect UID, mode and
actual access ACL through descriptor-bound mechanisms (for example libacl
`acl_get_fd` where applicable). Require UID 0 and no effective untrusted write
access to files or to directories that allow rename/unlink/replacement. Evaluate
named users/groups and `ACL_MASK`; mode group bits can represent the ACL mask,
not the whole ACL. The [acl(5) manual](https://man7.org/linux/man-pages/man5/acl.5.html)
explains the access algorithm. Default ACLs on directories affect **newly
created** objects, not retroactively the access ACL of existing files; inspect
them for the updater's creation path and validate actual ACLs after creation.
`getfacl` can fall back to mode-only output where ACLs are unsupported
([getfacl(1)](https://man7.org/linux/man-pages/man1/getfacl.1.html)); that
fallback is not evidence that the required ACL inspection succeeded. Define and
test how to distinguish a valid minimal ACL from unsupported/error cases;
unknown is UNAVAILABLE. Capabilities, LSM policy, UID mappings, group
membership and privileged processes must be included in the deployment model;
mode/ACL checks alone cannot establish every process's authority.

A regular file can have hard links. As a conservative profile restriction,
require `st_nlink == 1` for policy and lock objects and inspect their protected
ancestors; this does not detect existing open writable descriptors, races, or
privileged mutation. [link(2)](https://man7.org/linux/man-pages/man2/link.2.html)
documents hard-link behavior. Metadata before/after reading and a second hash
can catch some mutations but cannot prove none occurred. The candidate relies
on no pre-existing untrusted writer and all trusted writers participating in the
lock protocol; establishing that at installation and protecting against
out-of-protocol trusted writers remain explicit assumptions, not facts inferred
from `stat`. If they cannot be established for the deployment, UNAVAILABLE.

## Stable snapshot candidate

After authority checks and under the cooperative update lock, read at most
1 MiB + 1 from the **same opened policy descriptor**, rejecting overflow and
short/error conditions as appropriate. Copy into a private anonymous
`memfd_create(MFD_CLOEXEC | MFD_ALLOW_SEALING)`. After writing completely, add
`F_SEAL_WRITE | F_SEAL_SHRINK | F_SEAL_GROW | F_SEAL_SEAL`, verify with
`F_GET_SEALS`, then rewind/read a single immutable byte buffer from the sealed
object for SHA-256, strict parsing and downstream consumption. No writable
shared mapping may exist when adding `F_SEAL_WRITE`; a failed seal, short read
or inconsistent length denies. `F_SEAL_FUTURE_WRITE` alone is insufficient
because existing writable mappings can remain writable. The kernel documents
these behaviors in [memfd_create(2)](https://man7.org/linux/man-pages/man2/memfd_create.2.html)
and [file seals](https://man7.org/linux/man-pages/man2/F_GET_SEALS.2const.html).

This makes the **captured bytes** immutable after successful sealing, not the
source coherent while copying. Preventing concurrent source mutation relies on
the verified authority and cooperative lock assumptions above. Copying and
sealing a mixed source is not a snapshot of a proven earlier file version. The
snapshot and buffer are private to trusted processes: restrict fd passing,
ptrace and debug access; hash and parser must consume the same buffer, not
reopen the original path. On every error close descriptors and discard buffers;
CLOEXEC prevents accidental inheritance across exec but not fork. The anonymous
object disappears only after **all** references close, including inherited or
passed descriptors. Memory/swap confidentiality, core dumps, trusted consumer
mutation after parsing, and cleanup after abnormal exits require deployment
controls and tests; no confidentiality or host-compromise guarantee is claimed.

## `flock` and update coordination

Proposed candidate: root-owned, root-protected, pre-created `policy.lock`,
opened by both loader and updater through the protected directory; both use
`flock(2)` on the **same inode** (loader shared, updater exclusive). The inode is
never renamed, deleted or recreated during service lifetime or recovery; policy
publication replaces `policy.json`, **not** the lock file. Secure resolution,
owner/mode/ACL/link and mount checks apply to the lock as well. Protect the
parent directory and enforce the administrative update protocol; an inode
comparison made once cannot protect against a privileged non-cooperating
replacement. If identity cannot be kept stable, do not claim coordination.

`flock` is advisory and associated with an **open file description**; duplicate
FDs and forked children may retain it, and it is released after explicit unlock
or closure of all associated descriptors, not simply because one process
exits. Separate opens have separate descriptions. See
[flock(2)](https://man7.org/linux/man-pages/man2/flock.2.html). Do not mix
`flock` with another lock API and assume they coordinate. Use `LOCK_NB` with a
monotonic deadline (proposed 5 seconds) and bounded retry; timeout, interrupted
or uncertain lock state returns UNAVAILABLE without proceeding. Control fd
inheritance and ensure a child cannot prolong a dead holder unexpectedly.

The design contract requires the admission reader to retain its shared lock
from policy snapshot through the admission decision; updater takes exclusive lock
for full publication. No admission gate exists today. Proposed updater writes a
new validated policy in the same protected directory, `fsync`s the file,
atomically `renameat`s it, and `fsync`s the directory before reporting update
completion. [rename(2)](https://man7.org/linux/man-pages/man2/rename.2.html)
and [fsync(2)](https://man7.org/linux/man-pages/man2/fsync.2.html) describe
atomic pathname replacement and directory durability considerations. Atomic
rename is not by itself crash durability. Lock release on process death does not
roll back or certify a partially completed update; recovery must validate the
on-disk policy, handle temporary files and uncertain fsync/rename outcomes, and
deny new admissions while state is unresolved. Exact crash protocol, power-loss
semantics and trusted decision-record durability are still open and must be
verified on the candidate filesystem/storage. A lock does not stop hostile or
non-cooperating writers.

## Experiment matrix (all **NOT RUN**)

Run only in a disposable VM with an independent harness and separate untrusted
UID; capture profile and full per-case results. Altered profiles are separate
runs, not evidence for the baseline. Mount/ACL/power-failure tests require
appropriate privileges and must not be run on the developer workspace.

| ID | Setup and action | Expected observation / oracle |
| --- | --- | --- |
| P1 | Baseline protected root tree, matching policy; inspect kernel/package, mountinfo, namespaces, capabilities, ownership and actual ACLs. | Each fact matches recorded candidate; otherwise UNAVAILABLE. No result is admission. |
| P2 | Final and intermediate symlinks, `..`, magic links, FIFO/device and unsupported `openat2` flags. | No traversal/side-effect or hang; explicit rejection or UNAVAILABLE. No weaker fallback. |
| P3 | Race rename/replace intermediate directories and policy file under untrusted user, and deliberately weaken directory rights in a controlled negative fixture. | Untrusted operations denied or loader fails closed; descriptor identities and consumed bytes never resolve to an unchecked object. |
| M1 | Insert bind mount over ancestor/final component, plus private/shared propagation and namespace mismatch. | Mount crossing/invalid profile rejected; inability to prove stable topology is UNAVAILABLE. |
| M2 | Privileged harness toggles a mount during lookup and between inspection/read, including change then restore. | Demonstrate actual prevention or fail closed; matching endpoint snapshots alone are not a PASS. Privileged attacker is only a test instrument. |
| A1 | Add named-user/group write ACL with effective and masked permissions; vary default ACL for newly created policy. | Evaluate actual effective access and post-create ACL; untrusted write rejected. Missing ACL support/inspection is UNAVAILABLE. |
| A2 | Hard-link policy/lock; retain pre-open writable FD before permissions are tightened; mutate in place. | Link restriction enforced; show why existing writer violates baseline and causes denial or remains an explicit unverified assumption, never PASS based only on mode. |
| S1 | Valid bytes, exactly 1 MiB, 1 MiB + 1, short read, I/O failures, sealed memfd mutation/truncate/writable mmap attempts. | Bounded read; overflow/errors deny. After sealing, permitted reads yield identical bytes for hash/parser/consumer; forbidden writes fail. |
| S2 | Mutate source during copy; stop process or leak descriptor through fork/exec. | No false coherent-source claim; prove lock/authority protection or deny. Verify last-reference cleanup and documented inheritance behavior. |
| L1 | Separate cooperating loader/updater processes contend on same lock inode; timeout and `EINTR`. | Shared/exclusive ordering, bounded timeout; no snapshot/admission on uncertain lock. |
| L2 | Replace lock pathname deliberately; inspect inode and process-lock ownership; fork/dup then kill original holder. | Show split lock hazard is prevented by protected protocol; lock remains held while any shared description survives. |
| L3 | Kill updater before/after file fsync, rename and directory fsync; repeat with actual VM power cut and restart on specified storage. | Deny while recovery uncertain; only documented old/new policy accepted after recovery. Record every outcome, not just success. |
| L4 | Controlled revocation before/after future admission point, held-lock timeout and crash. | Only after gate exists: completed revocation before admission denies, later revocation follows in-flight rule; otherwise NOT RUN. |

Record raw commands, timestamps, return codes, kernel audit data where available,
and fixture hashes. Reproducible harness and acceptance thresholds remain to be
written; an absent privilege/capability causes UNAVAILABLE or NOT RUN, not PASS.
Run enough iterations to expose races, but passing stress tests cannot prove the
absence of all possible races.

## Decisions and status criteria

- **PASS (future, per check):** all mandatory facts for the exact tested profile
  are established by implemented mechanisms and independent integration tests.
  A snapshot-stage PASS says only what the snapshot contract explicitly covers;
  it is neither policy authorization nor planner ADMIT.
- **FAIL:** an observed policy/authority violation, unsupported allowed-value
  mismatch, unsafe path, or failed invariant. Do not produce a trusted snapshot.
- **UNAVAILABLE:** necessary feature, inspection, trusted provenance, lock,
  resource, stable topology, test capability or outcome cannot be established;
  timeout and uncertain state are denial, not a warning. **NOT RUN** means no
  test evidence and is not a pass. Exact distinction for missing versus invalid
  configuration should follow the policy-loading contract.

**Go for implementation as isolated, fail-closed experiments:** bounded parsing,
`openat2` wrapper without fallback, descriptor-bound metadata/ACL probes,
sealed memfd mechanics and a `flock` harness may be prototyped independently.
None may change the public scaffold from `UNAVAILABLE` or assert trusted snapshot
status. **No-go for claiming a trusted snapshot:** safe final-object open,
checked-chain binding, full ACL/capability authority, stable mount topology,
pre-existing writers and same-byte consumption need concrete design and tests.
**No-go for updater coordination/admission:** trusted lock identity, deadline,
publication/recovery under crash, admission gate and concurrent revocation have
not been implemented or tested. Keep all unresolved guarantees explicit.
