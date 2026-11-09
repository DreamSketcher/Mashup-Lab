# Project–Plan Binding Specification — draft v0.1

Status: **design proposal only**. Binding, execution validation and audio
rendering are not implemented. The existing `plan` and `validate-plan`
commands do not create or verify a binding. This document complements the
[project format](project-format-specification.md), [timeline plan](timeline-plan-specification.md)
and [reproducibility](determinism-reproducibility-specification.md) drafts;
it does not change the v0.1 project or plan JSON formats.

## Goal and limits

A binding ties an exact project file, exact source files and exact plan file
together for a proposed execution. Before execution, independently validate the
objects and recompute the plan from the verified project, then compare every
plan value. Hashes alone establish byte identity, not that a plan was actually
calculated from a project. Nor do they authenticate the author: an attacker who
can replace all artifacts can replace their hashes too. Authenticity and
signatures are outside MVP.

Strict MVP policy: **any byte change** in the project or any declared source
invalidates an existing binding, including comments, formatting, unrelated clip
gain and unused declared sources. The unchanged plan may still be geometrically
correct, but is not eligible for execution under the old binding. To proceed,
explicitly create a new binding and regenerate/verify the plan. A changed
source hash also requires an explicit project edit and review of affected
boundaries and synchronization, as specified in the project format.

## Where provenance lives

Propose a separate UTF-8 JSON sidecar, supplied explicitly alongside the
project and plan; neither file is modified. The sidecar is distinct from the
post-render manifest and from the render environment profile. It is an
untrusted claim, not a signature. Its v0.1 fields are:

| Field | Meaning |
| --- | --- |
| `binding_version` | String `"0.1"`, sidecar schema version. |
| `project_sha256` | SHA-256 of the exact project bytes, including BOM, comments and line endings, before UTF-8 decoding. A BOM is still subject to project parsing rules. |
| `project_schema_version` | Validated project schema version. |
| `plan_sha256` | SHA-256 of the exact bytes of the supplied UTF-8 plan JSON file. |
| `plan_version` | Validated plan schema version. |
| `planner_id` | Exact planner implementation, contract version and build-manifest digest, as defined below; not an audio algorithm version. |
| `sources` | Array in project source order, one record per declared source. |

Every hash is lowercase 64-character hexadecimal SHA-256. A source record
contains exactly `id`, `sha256`, `sample_rate`, `channels`, `frames`,
`wav_format` and `bits_per_sample`; `wav_format` is `"pcm_integer"` in MVP.
These are measured from the verified source, not merely copied from the project.
Project v0.1 does not store source bit depth, so it must be read from the WAV.
Source paths remain in the project and are resolved relative to that project's
directory under the project format's path restrictions. The sidecar is not a
search index and does not authorize alternate paths or sources.

Unknown fields, duplicate JSON keys, invalid types, malformed hashes, missing
or duplicate source records and unsupported versions are errors. Full parser
limits must be specified before shipping the feature. The sidecar is not a self-contained execution plan.

## Planner identity

For MVP, retain one field with the exact ASCII syntax
`mashup-lab-timing/<contract>/sha256:<digest>`, where `<contract>` is `0.1`
for the timing semantics defined by the v0.1 project and plan specifications,
and `<digest>` is 64 lowercase hexadecimal digits. For example, the shape is
`mashup-lab-timing/0.1/sha256:` followed by a real build-manifest digest. The
contract version is not the planner build version or the JSON plan version.
Any incompatible change to position conversion, rounding, clip-length or
intersection semantics needs a new contract version. A build or CLI-only change
does not automatically change that contract version.

The digest identifies the exact raw bytes of a UTF-8 build manifest distributed
with a trusted planner build. See the separate
[planner build manifest specification](planner-build-manifest-specification.md)
for its proposed schema, trust policy and runtime verification. Different build
digests are distinct identities even when they implement the same contract; no
cross-build equivalence is claimed in MVP. The planner ID is a declared identity
checked by the verifier, not proof of the historical process that created a file.
Neither the manifest verifier nor an approved build exists yet.

Plan hashing is deliberately **byte-based**: reformatting plan JSON requires a
new binding even when its parsed values are identical. Semantic comparison in
the verification procedure below ignores JSON object key order and whitespace,
and compares exact key sets, JSON value types, array order and exact integer
values recursively. Missing fields are never equivalent to `null`; booleans are
not integers. For plan v0.1, integer fields must be JSON integer tokens, not
floating-point tokens such as `1.0` or `1e0`; no conversion through binary
floating point is allowed. Duplicate object keys, nonstandard NaN/Infinity and
unknown fields are errors. Exact arbitrary-precision integer parsing is required,
including values above 2^53. This avoids specifying a canonical JSON
serialization. Equal parsed plans can still have different byte hashes.

## Binding creation

A future binding creator must:

1. Read a stable snapshot of the exact project bytes; calculate its hash, parse
   those same bytes and validate schema, references and paths.
2. Snapshot and verify every declared source: hash its complete bytes and check
   WAV format, rate, channels and frame count against the project. Validate clip
   ranges and all remaining project constraints. Record measured source facts.
3. Calculate the plan from this validated project using the identified planner,
   independently validate its geometry and serialize it as UTF-8 JSON. Hash the
   exact serialized bytes. Populate the sidecar using the validated values.
4. Publish the project reference, plan and sidecar as a consistent set. If any
   step fails, do not publish a binding as valid. Atomic publication strategy is
   implementation-dependent and must be documented; writing two files separately
   is not itself an atomic transaction. Consumers must verify the set regardless.

## Verification before execution

Verification is fail-closed. It must operate on stable snapshots of the exact
bytes to be used, not merely on pathnames that may change between checking and
use. In order:

1. Strictly parse the sidecar and plan, verify the plan byte hash and validate
   the plan independently. Check the plan version against the sidecar.
2. Hash the project snapshot, compare it with the sidecar, then parse and
   validate that same snapshot. Check schema version and all project constraints.
3. Resolve and snapshot **all declared sources**, including unused ones. Verify
   each full-file hash against both project and sidecar; validate format and
   actual metadata against both where the project contains those fields. Compare
   the complete ordered source list, not just entries present in the sidecar.
4. Recompute the expected plan with the compatible identified timing model from
   the validated project; compare the entire parsed plan structure, including
   clip order, all boundaries, durations, overlap entries and total frames.
   Recalculation is a binding verification step, not a second calculation by the
   renderer. On mismatch, abort even if the supplied plan is internally valid.
5. Separately validate execution requirements and the selected render profile:
   supported algorithms and versions, options, format, resources and output-path
   safety. Only after all checks may a backend consume the **verified plan's**
   frame positions and lengths and the verified source snapshots. It must not
   independently interpret bars, beats, ticks or BPM.

A planner identity mismatch is an error unless an explicitly supported verifier
for that exact identity is available. Compatibility across planner versions is
future work; merely having the same schema version is insufficient. The profile
check must compare the requested profile to the actual execution environment;
no profile is currently defined. A changed audio algorithm or environment does
not by itself alter timeline binding, but a mismatch with the requested render
profile prevents execution under that profile. Choosing another profile is an
explicit new execution decision and must be recorded in its render manifest;
it cannot be reported as the original fixed-environment render.

### Snapshot and publication safety

Hashing a file and reopening its path later permits replacement or in-place
mutation between verification and use. An open descriptor alone does not prevent
in-place writes. The future implementation must provide stable verified bytes,
for example by copying to private immutable snapshots, hashing and decoding
those snapshots, and using those same snapshots throughout execution. If it
cannot guarantee that, it must fail rather than claim verified execution. The
same applies to project and plan bytes. Avoid output paths that overwrite inputs;
failed verification must not leave a result represented as a successful render.
Disk space, symlinks and resource limits need explicit implementation review.

A copy can itself race with a writer. Check file identity and metadata before
and after copying and recheck the original hash when feasible; these checks can
detect many changes but do not prove that no concurrent modification occurred.
A source snapshot is acceptable only if its own full-byte hash matches the
expected hash from the validated project (and, at verification, the sidecar),
and all decoding and execution use that same protected snapshot. For project
and plan snapshots, compare their own bytes to the expected sidecar hashes.
This identifies the bytes used, subject to SHA-256 collision resistance; it does
not establish that the original file or a collection of files was ever observed
in one globally atomic state. During binding creation, the captured project
bytes define the version being bound and its declared hashes constrain source
snapshots. If a coherent original filesystem state is required, use a filesystem
snapshot or reliable locking with writers cooperating; metadata checks alone are
insufficient. Failure to protect the private snapshot from modification, or any
hash mismatch, is an error. Handle path resolution and symlink races securely;
no path validation by itself constitutes a snapshot guarantee.

A recommended publication strategy is to write and fully validate the plan and
sidecar in a private temporary directory, with the project reference, then make
the completed directory visible under a fresh unique binding identifier using
an atomic same-filesystem directory rename where the platform supports it. Do
not replace an existing published directory in place. This is a publication
strategy, not an automatic durability or filesystem-snapshot guarantee: crash
recovery, fsync requirements and platform semantics must be specified by the
implementation. Readers must still verify all artifacts and source snapshots.
If atomic publication is unavailable, do not advertise the set as atomically
published; a separate completion mechanism must be designed and documented.

## Reuse and execution admission

A binding is reusable, not a single-use execution token. After a failed render,
it may be used again only after the full verification and execution/profile
checks are repeated against fresh stable snapshots. Every actual render gets its
own render manifest. A previous successful verification cannot authorize later
reads of mutable paths. The future execution gate must accept only the validated
project, verified plan and protected source snapshots from that same check,
with an explicitly validated render profile; unverified artifacts never reach
the backend. Resource failures may be retried without editing a valid binding.

## Diagnostics and acceptance cases

Errors should distinguish invalid syntax/schema, project byte mismatch, source
identity or metadata mismatch, plan byte mismatch, planner incompatibility,
plan/project geometry mismatch, profile incompatibility and unsafe execution.
Include the relevant source or clip ID where safe; do not print audio contents.
Do not silently bypass errors or automatically rebind.

Before claiming implementation, test at least:

- unchanged project, sources and plan verify; repeated creation yields equivalent
  semantic binding information with a documented serialization policy;
- project whitespace or gain change invalidates the old binding even if geometry
  is unchanged; a changed source fails even when its WAV metadata matches;
- altered plan bytes fail the hash check, and a self-consistent but forged plan
  with an updated sidecar hash fails recomputation; missing or reordered clips
  and overlaps fail as appropriate;
- missing/extra/reordered source records, changed WAV metadata, unknown schema or
  planner, malformed JSON, and unsupported profile fail closed;
- changing the actual environment/backend is handled by profile compatibility,
  not falsely attributed to stale timing; fixed-profile mismatch blocks execution;
- JSON with reordered keys compares equal, while missing versus null, integer
  versus float, duplicate keys and different array order do not; large integers
  remain exact;
- unknown planner identity or altered build manifest fails; a different build
  is not accepted merely because the timing contract version matches;
- replacement or in-place mutation during copying or between checking and use
  cannot make the backend consume unchecked bytes; failed verification produces
  no successful render;
- a retry after resource failure revalidates inputs and can reuse an unchanged
  binding; each completed render records its own manifest.

The above tests prove behavior within their fixtures, not author authenticity,
legal rights, arbitrary-platform bit identity or audio quality.

## Proposed implementation stages

1. Strict sidecar schema parser and validator, including planner identity syntax.
2. Binding creation from verified snapshots and documented publication behavior.
3. Binding verification, including independent plan validation and recomputation.
4. An execution gate handing only verified data to a future renderer.

The stages should be tested independently; DSP backend selection follows them.
