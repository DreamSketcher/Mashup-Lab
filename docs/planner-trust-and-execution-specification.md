# Planner Trust and Execution Specification — draft v0.1

Status: **design proposal**. A policy schema parser and untrusted file
comparison are implemented; no trusted policy store, launcher, image
verification, isolation monitor, binding or audio execution currently exists.
This document refines the [build manifest](planner-build-manifest-specification.md)
and its [test contract](planner-build-manifest-test-contract.md); it does not
change the project, plan, binding sidecar or build manifest schemas.

## Purpose and trust boundary

The objective is a fail-closed decision on whether an identified timing planner
may recompute a project plan. Three distinct statements must not be conflated:

1. **Identity:** exact manifest bytes hash to the requested ID, and the specified
   image and its referenced artifacts match their digests.
2. **Local authorization:** a trusted operator's policy approves this ID and
   image for this purpose. A matching SHA-256 is not authorization or authorship.
3. **Execution conditions:** a trusted launcher starts that image under checked
   restrictions. This is a claim under the assumptions below, not proof that a
   malicious or compromised host cannot interfere.

The operator, policy storage, launcher, runtime, kernel, image verifier and
snapshot storage are trusted components of the local installation. An attacker
is assumed able to supply or modify projects, sidecars, manifests, source files,
plans and their paths, and to control ordinary input data. They cannot change the
trust policy or the trusted computing base. A malicious administrator, root,
compromised runtime/kernel, hardware, or an approved but malicious planner is
outside this model. Image approval does not establish authorship, correctness,
licensing, or reproducible build provenance. Use of these data in a service
requires a separate security review, resource controls and sandbox threat model.

## Root of trust: locally administered policy

The proposed MVP root is a **local operator-managed allowlist**: no network trust
service and no automatic trust-on-first-use. The operator chooses and installs
its bytes through a trusted deployment channel and protects the directory and
file against modification by untrusted users. The verifier is configured by the
trusted installation to use that policy location; a project, sidecar, planner,
manifest, CLI input from an untrusted request, or environment variable must not
redirect it or add an entry. Exact ownership, permissions and safe-open checks
must be specified for each supported platform before implementation; if the
platform cannot establish the configured protection, admission is unavailable
and fails closed. The policy itself may be readable; secrecy is not the trust
mechanism.

Proposed UTF-8 JSON policy v0.1, parsed with duplicate-key rejection, exact
field sets and strict types, contains:

- `policy_version`: string `"0.1"`.
- `entries`: array of objects with exactly `planner_id`, `image_digest`,
  `platform` and `status`. IDs follow the build-manifest specification;
  `image_digest` is the concrete single-platform OCI manifest digest in
  `sha256:<64 lowercase hex>` form, not a tag or index. `platform` is the exact
  OCI platform string. `status` is `"active"` or `"revoked"`.

A planner ID must occur at most once regardless of status; unknown fields,
invalid types, invalid IDs/digests or malformed/unsupported policy versions
invalidate the **entire** policy. An empty entries list is valid and trusts no
planners. All values must agree with the independently validated build manifest.
A sidecar's planner ID selects a matching active entry but is never the source
of approval. The manifest bytes must hash to that ID and its image digest and
platform must exactly match the active entry; matching the sidecar alone is not
enough. Unlisted, revoked, mismatched, unreadable, absent, malformed or
unsupported policy means **deny**, never warn-and-continue or fall back to a
host Python. A manifest is not trusted merely because it parses.

The experimental `compare-policy` command performs only structural parsing and
claim comparison against the caller-supplied policy file. It emits MATCH,
NOT_LISTED, REVOKED, MISMATCH or UNAVAILABLE, and always states that trust and
execution were not checked. MATCH is not the authorization described above. The
parser applies the manifest JSON resource limits and a maximum of 1,024 entries.
It does not validate policy ownership, permissions, protected directories, safe
snapshot semantics or image contents. It is not a trusted admission gate.

An operator may remove or revoke an entry via a trusted policy update. Each new
admission uses a fresh safely read policy snapshot; verification cached from a
prior run is not sufficient. This draft does not promise immediate interruption
of work already admitted when policy changes. The proposed [trusted policy loading contract](trusted-policy-loading-specification.md)
defines snapshot, coordinated update and admission-point requirements; a
supported-platform implementation must still specify and verify the mechanisms. Report the SHA-256 of the
exact policy snapshot and the selected ID in a decision record; that hash is
for audit and does not itself make the policy trusted. Avoid recording sensitive
project content. Optional signatures or remote policy distribution need a
separate key, update and revocation design; they are not part of v0.1.

The [launcher lifecycle and bootstrap contract](planner-launcher-lifecycle-specification.md)
specifies pre-execution ordering, runtime object identity and launcher trust.
Its requirements apply in addition to the following admission sequence.

## Admission and actual invocation

The planner is not allowed to self-attest by printing a version or ID. The
following checks must be performed by the trusted launcher/verifier, in order,
against protected snapshots. Any error aborts the admission attempt:

1. Read the configured trusted policy securely; strictly parse it. Snapshot the
   requested manifest and sidecar as untrusted bytes. Hash and validate the
   manifest; match sidecar ID, contract, active policy entry, image digest and
   platform as above. Obtain only the approved image by immutable digest; do not
   let an input choose a new trust root or arbitrary executable.
2. Verify the actual OCI manifest and all referenced config/layer digests, and
   materialize the verified image in a protected immutable store. Validate the
   concrete image's platform and the interpreter/dependency artifact paths,
   digests and metadata against the manifest. The image digest identifies the
   planner code, interpreter, standard library and native dependencies as part
   of the full image. Manifest `engine_version`, Python version and package
   version strings are claims; verifying artifact bytes and image identity does
   not independently prove that those labels or claimed build provenance are
   truthful. Trust in the approved build and its review remains an operator
   decision. Build-time dependency provenance is distinct from runtime identity.
3. Construct the exact invocation from the verified manifest and local policy,
   using the **same verified immutable image**, not an image tag or a later
   mutable path. Create the runtime object without starting planner code, then inspect it via
   trusted mechanisms as required by the lifecycle contract. Verify the
   concrete image identity, platform, effective entrypoint/arguments, mounts,
   read-only root, network state, environment and isolation settings against the
   approved policy. On mismatch or if a needed fact cannot be verified, stop the
   container and deny. Release the start barrier only after checks succeed.
   Do not trust values reported solely by the planner inside the container.
4. Pass only protected validated data snapshots as read-only data; they must not
   be executable/import paths. The launcher binds result collection to this
   invocation and validated input snapshots. Verify the returned plan against
   the binding contract before any future audio execution. Prevent untrusted
   inputs from overriding the interpreter, entrypoint, image, mounts or policy.
5. Record the policy snapshot hash, manifest ID, verified image digest,
   platform, launcher/runtime identifiers, checked isolation profile and
   decision status. A render, if one is later admitted, has its own manifest.

The start barrier, runtime inspection interface, immutable store, artifact
layout, permitted invocation arguments and testable configuration must be
specified for each supported runtime before shipping. If the runtime cannot
provide these controls without a check/use race, report the required check as
unavailable and deny. Inspecting a configuration does not independently prove
that a runtime or kernel enforces it, nor does this contract provide remote
attestation or measure arbitrary process memory. Host kernel, CPU and runtime
behavior remain assumptions; identify them in the execution record and apply
separate reproducibility/profile checks. A previously running process that only
claims an ID cannot be retroactively admitted by this procedure.

## Isolation: required conditions versus evidence

The declared `offline-readonly-v1` profile requires offline execution,
read-only image root, no writable or host-mounted executable/import paths, no
user site or injected Python/preload hooks, and an allowlisted environment as
specified in the build manifest. The implementation must define the precise
environment allowlist, mounts, privileges, network namespace behavior and
runtime configuration for each supported platform **before** claiming support.
Outputs may use a restricted writable location that cannot shadow any code or
library path. Resource limits and filesystem permissions must also be defined.

Distinguish: (a) a restriction requested in configuration, (b) configuration
observed by the trusted launcher, and (c) behavior checked in integration tests.
None alone proves security against a hostile host. Where feasible, integration
tests must actually attempt forbidden network access, code-path mutation and
environment injection. No isolation approval follows just from an image label,
manifest value or container runtime being installed.

## Decisions and diagnostics

For each required check, record one of **PASS**, **FAIL** or **UNAVAILABLE**:
FAIL means a violation was observed (such as a revoked ID or digest mismatch);
UNAVAILABLE means the check could not be completed (such as inaccessible policy,
missing capability, unsupported runtime or failed inspection). Both deny
admission. Unexecuted later checks are **NOT_RUN**, not PASS. The overall result
is ADMIT only if every required check passes; parsing a valid manifest is not an
ADMIT. Do not confuse an explicit policy denial with a transient inability to
read policy. Avoid leaking secrets or untrusted audio contents in diagnostics.

## Independent acceptance scenarios

In addition to the build-manifest test contract, implementations must show:

- a valid manifest and image with an empty allowlist is denied; the same exact
  ID/image/platform explicitly approved by the local operator can proceed to
  image and invocation checks, not automatically to ADMIT;
- an attacker replacing both manifest and sidecar ID cannot gain trust; nor can
  an attacker point an untrusted request at a different policy file;
- policy absent/unreadable is UNAVAILABLE; an accessible policy with a revoked
  or unlisted ID is FAIL; both deny and do not launch;
- after policy revocation, a new attempt fails even if an earlier attempt passed;
  no claim is made about cancelling an already admitted invocation;
- approved manifest with different image, platform, altered image layer,
  interpreter or dependency fails independently of a process printing the
  expected ID; a runtime lacking trustworthy inspection returns UNAVAILABLE;
- injected environment, shadow mounts, modified entrypoint or network-enabled
  settings are rejected before planner work starts. A fake runtime reporting
  compliance is not a substitute for real integration testing;
- replacing or modifying input files cannot make the planner use bytes different
  from verified protected snapshots; any failure prevents successful admission.

Schema tests, trust-policy tests and real runtime integration tests must be
reported separately. Passing the first two without the third does not justify
an isolation claim. This specification does not assert that current code provides
any of these guarantees.
