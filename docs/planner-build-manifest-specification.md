# Planner Build Manifest Specification — draft v0.1

> **Scope update:** This document is optional trusted-execution research, not a
> prerequisite for the Mashup Lab music MVP. For current priorities and the
> simpler render-time binding direction, see [MVP scope](mvp-scope.md). Historical
> references to “MVP” below apply only to the proposed trust subsystem.

Status: the manifest schema parser and byte identity are implemented; trust,
image verification, launcher and an approved build profile are not. This
specifies a future way to identify and admit a particular timing-planner build
for [Project–Plan Binding](project-plan-binding-specification.md). It does not
change the project, plan or binding sidecar schemas. It does not select an audio
backend, establish authorship, prove an implementation correct, or promise a
reproducible build.

## Trust model

A manifest digest identifies exact manifest bytes, not a trusted author or a
running process. Before verification, a local operator must install a trust
policy mapping accepted `planner_id` values to approved immutable execution
images and a trusted launcher/verifier. A sidecar may name an ID but must never
add it to the allowlist, choose executable code, or trigger a download or run of
arbitrary code. Unknown, revoked or unsupported IDs fail closed. The proposed local trust root and admission procedure are defined in the
[trust and execution specification](planner-trust-and-execution-specification.md).
Remote policy distribution and signatures are outside MVP; if used, signatures
need their own key and revocation policy. A signature alone
is not proof of correctness or of the code currently executing.

The MVP threat boundary assumes the launcher, container runtime, host kernel,
trust policy and storage isolation are trustworthy. It does not defend against
a compromised host or malicious administrator. A local unconfined Python
process reporting its own version/hash is **not** sufficient evidence that the
claimed build is executing. Hashes do not verify past execution or authorship.

## Manifest and identity

A build manifest is a standalone UTF-8 JSON file. Its SHA-256 is calculated over
its **exact file bytes**, without normalization; formatting changes the digest.
The sidecar `planner_id` has the form
`mashup-lab-timing/<contract>/sha256:<manifest-digest>`, with lowercase 64-digit
hex digest and a contract string of `0.1` for the current timing semantics.
The manifest does not contain its own digest or full `planner_id` (avoids a
circular hash). Do not confuse the timing contract version with plan schema,
engine release, Python version, or build identifier.

MVP manifest top-level fields, all required, with no unknown fields:

| Field | Type and meaning |
| --- | --- |
| `manifest_version` | String `"0.1"`. |
| `implementation` | Fixed string `"mashup-lab-timing"`. |
| `planner_contract_version` | String `"0.1"`. Must equal the contract in `planner_id`. |
| `engine_version` | Nonempty release/version string identifying the implementation, distinct from the contract. |
| `build_id` | Nonempty producer-assigned build label for diagnostics; not a security identifier. |
| `git_commit` | Full lowercase 40- or 64-digit commit object ID, or `null` if unavailable. Informational, not proof of source or build contents. |
| `git_dirty` | Boolean, or `null` if unknown. A commit does not identify uncommitted changes; even `false` is a claim, not independent proof. |
| `python` | Object: `implementation`, `version`, `executable_path`, `executable_sha256`. Exact version string and path/digest of interpreter **inside** the image. |
| `dependencies` | Array of objects with `name`, `version`, `artifact_path`, `artifact_sha256`; exact installed distribution metadata and digest of its immutable packaged artifact inside the image. Empty array allowed. |
| `execution_image` | Object: `platform`, `oci_manifest_digest`, `entrypoint`, `isolation_policy`. Specifies the concrete single-platform OCI image, not a mutable tag or multi-platform index. |

All listed digests are `sha256:` followed by 64 lowercase hexadecimal digits,
except the bare digest component of `planner_id`. Paths are absolute POSIX paths
inside the image, normalized, without `..` or backslashes, and refer to regular
files (existence and type are checked only at admission). Schema parsing also
rejects NUL and unpaired surrogates; valid JSON escaped surrogate pairs decode
to a single Unicode scalar and are accepted. Escaped and literal forms have
different byte hashes. Entrypoint arguments may be empty except
for the executable. Platform components use lowercase ASCII letters, digits,
period, underscore and hyphen, beginning with an alphanumeric. Dependency
names use lowercase normalized Python distribution names (`[a-z0-9]+` groups
separated by single hyphens); names must be unique
and entries sorted by name. `entrypoint` is a nonempty array of literal argument
strings, not a shell command. `platform` is an exact OCI `os/architecture`
string, optionally followed by `/variant`; `isolation_policy` is the literal
`"offline-readonly-v1"` defined below. The manifest describes the actual image,
not a wishlist of packages. The complete image also contains Python's standard
library, transitive dependencies, native libraries and all planner code; its
OCI digest covers those contents even where no separate dependency entry exists.
Each dependency artifact must be installed from the named artifact during image
build; its hash and metadata are provenance claims checked during build and
covered by the image digest, not proof that installed files came from it.

Reject duplicate JSON keys, nonstandard NaN/Infinity, invalid types, malformed
hashes and unknown fields at every level. A verifier compares versions as exact
strings, not ranges. The manifest is outside the image it identifies: otherwise
its digest and image digest would be circular. Manifest provenance such as a
commit, a build label or package metadata does not establish trust. A future
implementation must define its image builder and artifact layout, including how
dependency records and their regular-file paths are generated and verified;
until then no build is eligible to claim this profile.

## Admitting a running planner

The trusted launcher and verifier must implement this procedure before
recomputation; any failure prohibits execution:

1. Take stable snapshots of sidecar and manifest. Parse strictly. Compute the
   manifest SHA-256 from its snapshot and check the exact `planner_id`, contract
   and locally approved policy. Do not treat `planner_id` syntax validation as
   a trust decision.
2. Obtain only the locally approved image for that ID. Verify its concrete OCI
   manifest digest and transitively verify referenced config and layer digests;
   reject tags, platform mismatch, missing blobs or unverifiable images. Check
   the recorded interpreter and dependency artifact paths/hashes and other
   manifest facts against the image. An independently checked digest does not
   make untrusted code safe: the approved image and launcher remain trusted.
3. Launch **that same verified image** with its recorded entrypoint. Under
   `offline-readonly-v1`, use a read-only image root, no network, no writable
   or host-mounted executable/import paths, no user site packages, no injected
   `PYTHONPATH`, `PYTHONHOME`, startup hooks or preload libraries, and a
   documented allowlist of environment variables. Disable implicit code download.
   Supply verified project/source snapshots read-only as data, not import paths;
   provide a separate restricted writable output location. Runtime configuration
   and mounts must not replace code, interpreter or libraries in the image.
4. Bind the verifier's recomputation result and its plan comparison to this
   particular invocation and its verified input snapshots. The future execution
   gate must use those same snapshots and the verified plan. Do not accept an
   identifier merely echoed by a process as attestation.

The concrete runtime, image extraction/verification and isolation enforcement
are not implemented. A successful check establishes that, under the stated trust
assumptions, the approved image was launched with the stated restrictions; it
is not a cryptographic measurement of arbitrary process memory. Host kernel,
CPU, runtime implementation and thread settings may still vary. Record them in
the execution/render manifest and apply the separate render profile; do not
claim cross-platform bit identity from this planner identity alone.

## Build reproducibility and tests

See the independent [test contract](planner-build-manifest-test-contract.md)
for pinned byte vectors and separate schema, trust and isolation acceptance cases.

This contract aims to **identify a particular build**, not guarantee that
rebuilding source produces identical image or manifest bytes. Timestamps, layer
ordering, compiler, dependencies and build tools may change artifacts. A future
reproducible-build claim requires a separately specified recipe, pinned inputs,
independent rebuilds and digest comparisons. A git commit alone is not a recipe.

Before implementation is advertised, acceptance tests must cover: unchanged
manifest and approved image; altered manifest bytes; altered contract or digest;
unknown/revoked IDs; incorrect image, interpreter or dependency hashes; missing
artifacts; platform mismatch; a sidecar attempting to select unapproved code;
injected environment/import paths and writable code mounts; and failures that
must not fall back to the host Python. Test a verified recomputation using the
same input snapshots that pass binding verification. These tests exercise the
chosen implementation and trust boundary, not correctness against a compromised
host. Build and execution machinery and its testable platform requirements must
be defined before claiming conformance.

## Parser resource limits

The implemented schema parser accepts at most 1,048,576 raw bytes, 32 nested
JSON objects/arrays, 4,096 Unicode code points per decoded string (including
keys), and 1,024 dependency records. File loading reads at most the byte limit
plus one byte, rather than reading the entire file before rejecting it. JSON
escaped control characters other than NUL are permitted where a string field
allows them; raw unescaped controls are invalid JSON. POSIX paths may contain
non-ASCII characters and are not Unicode-normalized; path identity remains exact.
These limits bound this parser only, not image verification or an entire service.

The byte cap bounds input size but Python JSON decoding can still amplify memory
usage through many small values; there is no separate total-member limit. A
service must apply additional process-level memory and time limits.
