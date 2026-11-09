# Planner Launcher Lifecycle and Bootstrap Contract — draft v0.1

> **Scope update:** This document is optional trusted-execution research, not a
> prerequisite for the Mashup Lab music MVP. For current priorities and the
> simpler render-time binding direction, see [MVP scope](mvp-scope.md). Historical
> references to “MVP” below apply only to the proposed trust subsystem.

Status: **design proposal only; not implemented**. There is no approved
launcher, runtime adapter or isolation profile. This contract refines the
[trust and execution specification](planner-trust-and-execution-specification.md)
and [build manifest specification](planner-build-manifest-specification.md).
It does not make a container secure merely by inspecting its configuration, and
it does not modify the project, plan, binding or manifest formats.

## Bootstrap: where launcher trust starts

The operator installs the launcher, runtime adapter, verifier, policy and their
dependencies through a trusted local administrative deployment process. The
installation's trust anchor is that administrative process and protected local
configuration, not a planner manifest or sidecar. The exact installation and
verification mechanism must be specified for each supported platform before
implementation is advertised. At minimum it must:

- protect executable files, libraries, configuration, policy and their parent
  directories from replacement or mutation by untrusted principals; verify the
  ownership, permissions and safe path resolution appropriate to the platform;
- protect the launcher's interpreter, dynamic libraries, plugin/module search
  paths and startup configuration, not just the launcher executable; prevent
  untrusted environment variables, working directories and user plugins from
  redirecting trusted code or selecting a different policy or runtime;
- restrict access to runtime control APIs and image/snapshot stores so that an
  untrusted user cannot create, replace, mutate or control objects in the
  admission namespace; protect credentials and runtime sockets accordingly;
- identify the deployed launcher, runtime adapter and relevant dependencies in
  the audit record, and define trusted update, rollback and revocation procedures.

The operator and deployment mechanism are trusted assumptions. A hash printed by
the launcher itself is diagnostic information, not independent proof of its
integrity. If installation integrity, policy protection or runtime control
cannot be established, admission is **UNAVAILABLE** and must deny. An observed
violation is **FAIL**. Neither permits fallback to a host Python process.

### Updates and compatibility

The [trusted policy loading contract](trusted-policy-loading-specification.md)
defines the proposed snapshot and policy-update ordering.

An operator installs a launcher update through the trusted administrative
process. It takes effect for **new** admission attempts only after the installed
version and its dependencies pass the local bootstrap checks. Policy entries
still authorize particular planner IDs and image digests, not arbitrary launcher
versions. Before using an existing policy, the new launcher must verify that it
supports its exact schema and the required isolation profile and can enforce the
checks in this contract; otherwise deny as UNAVAILABLE, not implicitly migrate,
weaken or replace policy. A policy edit requires the same trusted update path.
Record launcher/adapter build identifiers and the exact policy snapshot hash
for each attempt. Already admitted work is not automatically cancelled by an
update or revocation; immediate cancellation is outside this draft. New attempts
must read and validate the current protected policy again. Rollback must not
silently restore revoked policy; its operational procedure remains to be defined.

## Lifecycle and start barrier

The launcher must use a runtime-specific procedure that enforces the following
ordering. “Created” below means a runtime object that cannot execute planner
instructions until an explicit release/start. Runtime-specific lifecycle hooks,
init containers, image-supplied entrypoints and helpers must not run unchecked
planner or other image-supplied code before admission. If the runtime cannot meet
this precondition, it is unsupported for this profile.

1. **Bootstrap and authorize.** Verify the local installation and fresh policy
   snapshot, manifest, ID and approved concrete image as described by the trust
   specification. Prepare protected input snapshots and a restricted output
   location. Construct the full intended invocation and runtime configuration.
2. **Create without planner execution.** Create an isolated runtime object from
   the verified immutable image, without starting its entrypoint or executing
   planner code. Record its runtime-provided immutable identifier and bind it to
   this admission attempt. Creation itself may involve trusted runtime actions;
   any runtime or image hook that could execute untrusted code at creation must
   be disabled or rejected. Failure to verify this is UNAVAILABLE.
3. **Inspect the same object before release.** Using trusted runtime mechanisms,
   read back the created object's image identity, platform, effective entrypoint
   and arguments, environment, mounts, read-only root, privileges, networking,
   hooks and every other profile-required setting. Compare to the authorized
   configuration and reject unexpected or unverifiable values. Merely comparing
   the original request to itself is not inspection.
4. **Release and execute.** Start or release only that same verified object,
   using the runtime object identifier or a stronger runtime-provided handle,
   never a mutable name or a fresh lookup that could resolve to another object.
   A trustworthy mechanism must prevent replacement or mutation between
   inspection and release. The launcher must not allow planner work to start
   if this cannot be established. Collect output tied to this invocation and
   its protected snapshots, and then perform binding/plan verification before
   any future audio execution.
5. **Finish and record.** Record the object identity, verified image digest,
   launcher/adapter and runtime identities, policy snapshot digest, checks and
   decision. On failure, stop/remove the object as appropriate and do not report
   successful admission or render. An output file alone is not proof of success.

Creating a container without starting it can provide a pre-start barrier **only
if** the selected runtime guarantees that the inspected configuration and object
identity remain applicable at start and no unchecked code runs during create.
If restrictions become effective or observable only after start, pre-start
inspection alone cannot establish them. A runtime-specific implementation must
instead use a separately trusted launcher-owned gate that executes before any
planner code, checks those effective conditions via trusted mechanisms, and
releases planner execution only on success. The gate, its code, communication
channel and runtime behavior enter the trusted computing base and require their
own installation and tests. A gate inside an untrusted image, or a check after
planner instructions have already run, is not such a barrier. Neither approach
is declared implemented or universally available here.

## Object identity and mutation control

The inspected runtime object and released runtime object must be the same
runtime instance and immutable object, not merely objects with the same display
name, image tag, PID or requested configuration. The adapter must document the
runtime's identity, lifetime, namespace and reuse semantics, and how a start
operation addresses that exact object. Verify that the object has not been
removed, replaced or reconfigured, and that the image/configuration actually
used at release correspond to those inspected. Rechecking alone does not close
a check/use race if an adversary can mutate between the check and start: use a
runtime-supported immutable configuration/atomic operation or exclusive trusted
control over the object and runtime API. If these guarantees cannot be obtained,
admission is UNAVAILABLE.

Protected object control is a deployment assumption, not something implied by
a container ID. Runtime administrators and other privileged processes are
within the trusted boundary; this contract does not defend against their
malicious actions. Mutable bind mounts, runtime configuration edits, image
replacement, hooks and dynamic injection can break the equivalence even if the
object ID stays the same. Input snapshots and executable artifacts must remain
protected throughout use. Post-start observation can detect discrepancies and
stop work, but cannot retroactively prevent code already executed; all required
pre-execution conditions must be enforced before planner release.

## Evidence, decisions and acceptance

Keep requested configuration, pre-start runtime inspection, effective
post-start evidence and behavioral integration tests as distinct evidence. A
runtime's own reports rely on the trust assumptions above and do not establish
security against a compromised runtime or host. As in the trust specification,
checks are PASS, FAIL, UNAVAILABLE or NOT_RUN; an overall admission requires all
mandatory checks to pass. A planner's self-reported ID is not an independent
check. No guarantee is claimed until the platform implementation and its tests
exist.

Independent acceptance tests for a supported runtime must include:

- an untrusted user cannot replace launcher code, dependencies, trusted policy,
  runtime socket or planner object; missing protection is UNAVAILABLE;
- launcher update to a version lacking the policy/profile capability denies,
  while a supported update rechecks the existing policy; revocation affects a
  subsequent attempt without claiming cancellation of in-flight work;
- an image whose entrypoint writes a marker cannot write it during container
  creation or inspection; a failed inspection never releases planner work;
- a runtime hook that could execute image-supplied code before admission is
  rejected or shown disabled; lack of reliable evidence denies;
- replacement/recreation of object A as B between inspection and start, or
  configuration mutation in that window, is prevented or causes denial. A name
  reused for B must not allow B to start under A's approval;
- if a required effective restriction cannot be checked before planner code,
  an unsupported runtime fails closed; for a trusted gate, the gate is tested
  against attempted early execution and a failing or unverifiable condition;
- successful execution records the same verified object and image identity and
  uses the verified snapshots; policy, runtime-inspection, or output errors
  never result in an ADMIT or successful render.

Actual runtime integration tests must be run on each claimed supported platform.
Mocks can exercise control flow, but cannot demonstrate operating-system
isolation, runtime semantics, immutable object identity or installation security.
