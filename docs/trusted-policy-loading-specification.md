# Trusted Policy Loading — draft v0.1

Status: **design proposal, not implemented**. `compare-policy` only parses and
compares a caller-supplied file; it does not provide the guarantees below. This
contract refines the [trust and execution](planner-trust-and-execution-specification.md)
and [launcher lifecycle](planner-launcher-lifecycle-specification.md) drafts.
It is not evidence that a trusted launcher or supported operating-system adapter
exists.

## Authority and deployment

The trust anchor is an operator-controlled installation and administrative
process, not a hash delivered by a project, sidecar, manifest, planner, caller,
or the policy file itself. A protected launcher installation configures exactly
one absolute local policy path for an admission context. The launcher gets this
path from that protected installation configuration; untrusted CLI arguments,
request data, environment, current directory and project contents cannot
select, replace or override it. The policy must not be loaded from a remote URL
or an untrusted writable mount. An operator may configure a different path only
through the same trusted installation/update process, not through a request.

Only trusted administrators or a trusted update service acting for them may
modify the installation configuration, policy, parent directories and update
locks. The launcher itself needs read access; it does not need policy write
access. Untrusted users must not have write, rename or replacement authority,
including through ACLs, group membership, inherited permissions, hard links,
mounts, capabilities or a directory writable by another principal. Hashes can
detect changes to bytes, but do not establish who installed them. A hostile
administrator, compromised kernel, privileged runtime or untrusted filesystem
outside the protected installation remain outside this threat model. Failure to
establish protection is denial, not proof of a malicious actor.

## Reference candidate: Linux local filesystem

This is a proposed first adapter, **not supported or implemented**. A real
implementation must document its specific kernel/filesystem/runtime assumptions
and verify them with integration tests before claiming support. For this
candidate, trusted UID 0 installs a root-owned policy in a root-owned directory
chain from `/` to the file. No directory in that chain or the policy file may be
writable by group or other users, and no ACL, capability or mount behavior may
grant untrusted users equivalent write, replacement, or traversal manipulation
rights. All components must be local and on filesystems whose ownership,
permissions, locking and atomic-replacement semantics are understood and
verified; network, FUSE or unusual mounts must be rejected unless a separate
adapter proves equivalent guarantees. An open file descriptor alone does not
prevent in-place writes. Root and trusted updating processes remain assumptions.

The policy must be a regular file, not a symlink, device, pipe or directory.
The loader must resolve path components from a trusted directory descriptor with
no symlink traversal and no escapes, validate each opened component and the
final file using descriptor-based metadata checks, and read the final file via
that same descriptor. Prevent intermediate component swaps and mount changes,
not merely final-component symlinks; `lstat` followed by `open` is insufficient.
Linux `openat2`-style resolution constraints or an equivalently documented
component-by-component scheme may be used only when they provide the required
guarantees. File metadata checks alone cannot prove the absence of hostile
writers or mutation by trusted processes. ACLs and mount semantics require
platform-specific checks; inability to verify them is UNAVAILABLE and denies.
Define file size/JSON limits, permitted filesystem types and safe locking paths
in the adapter before implementation. This draft does not claim that mode bits
alone are sufficient or that any particular syscall sequence is already safe.

## Snapshot and admission point

An admission attempt must use one immutable snapshot of the exact policy bytes:

1. Bootstrap checks establish the trusted installation and select its configured
   path. Acquire a trusted lock that serializes **all cooperating policy updates**
   with new admissions. The lock itself and its directory must be protected and
   its identity stable; replacing the lock file must not create separate locks.
2. While holding that lock, resolve and open the policy safely, validate the
   authority and file properties, read within the documented resource limit,
   and copy the bytes to protected private storage or memory. Hash and strictly
   parse **those same bytes**. The hash is an audit identifier, not an authority
   or signature. Empty, invalid, unreadable or unprotected policy must not be
   replaced with an allow-all or cached earlier value. A policy with no entries
   is valid but authorizes no planner.
3. Compare the snapshot to the verified manifest/sidecar, check the selected
   active entry and perform the remaining required image, launcher and runtime
   pre-release checks. All decisions in this attempt refer to this same snapshot.
4. The **admission point** is the trusted launcher's successful recording of an
   ADMIT decision after all mandatory pre-release checks pass, while still
   holding the policy lock. Only then may it release the verified runtime object.
   An ADMIT record is not a claim that execution or rendering completed. The
   lock may be released after the admission point; later release or execution
   failure must be recorded separately and must not be reported as successful
   work. If recording the decision fails or its outcome is unknown, deny release.

A trusted updater acquires the same exclusive lock, writes and validates a new
policy in protected temporary storage, publishes it atomically using the
supported filesystem's documented semantics, and releases the lock only after
publication. If a revocation update **completes before the admission point**,
the attempt must use the new policy or fail; if admission occurred first, that
attempt may proceed and revocation affects subsequent attempts. The lock must
cover the entire policy read-to-admission interval, not just reading the file.
This ordering depends on all trusted writers cooperating and on trustworthy
filesystem and lock behavior. It is not a guarantee against privileged or
non-cooperating writers, a compromised host, or immediate cancellation of
already admitted work. If a policy update or lock operation has uncertain
completion, fail closed and resolve state before further admissions.

Hashing and parsing the snapshot prevents a later path replacement from changing
the policy bytes used for this decision; it does **not** establish that the
original policy was trusted without the installation and access checks. A
private snapshot must remain protected from modification. When no trustworthy
snapshot/locking mechanism exists, return UNAVAILABLE rather than silently
performing a weaker check. Failed admission must not release planner code.

## Results and evidence

Use the existing PASS/FAIL/UNAVAILABLE/NOT_RUN check statuses. Malformed policy,
unsupported policy version, unlisted or revoked ID, or mismatch is FAIL;
inaccessible policy, missing permission/ACL/mount evidence, unsupported
filesystem, unavailable locks or uncertain snapshot integrity is UNAVAILABLE.
Both deny admission. For an admitted attempt record at least the exact policy
snapshot SHA-256, selected planner ID and image, trusted launcher and adapter
identities, relevant validation outcomes and the admission decision. Do not
record project/audio contents. Record each actual render separately; a policy
comparison is neither an execution nor a render.

## Required integration tests before support claims

Tests must exercise the actual platform adapter, permissions, locks and
filesystem, not just mocked checks:

- trusted configured path succeeds; untrusted request/environment overrides,
  untrusted owner/write permissions, permissive ACLs, symlinked components,
  non-regular files and unsafe mounts are rejected or UNAVAILABLE as applicable;
- policy file and parent-component swaps and in-place writes cannot cause a
  decision to use bytes other than the protected validated snapshot; a hash
  matching attacker-supplied bytes does not authorize an untrusted file;
- a completed revocation before admission prevents release; an admission before
  the completed revocation follows the explicit in-flight rule. Test real
  concurrent updater/admission interleavings and lock-file replacement;
- unavailable locks or unknown read/update outcomes deny; malformed policy,
  revoked entry and inaccessible policy have distinct diagnostics;
- bytes compared, parsed and hashed are the identical snapshot, and subsequent
  admissions read fresh policy rather than a cached authorization;
- unsupported ACL/mount inspection is UNAVAILABLE rather than a silent PASS;
  no failure starts the planner or produces a successful render.

These tests provide evidence for the tested deployment, not a proof against a
compromised host or non-cooperating privileged writers. The safe installation,
policy loader, update service and launcher must be implemented before any such
claim can be made.
