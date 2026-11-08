# Planner Build Manifest — independent test contract, draft v0.1

Status: **test design only**. No manifest validator, trusted launcher, image
builder or binding verifier is implemented. This is an acceptance target for
[the build-manifest specification](planner-build-manifest-specification.md),
not evidence that it is satisfied. Do not treat fixture IDs or hashes as trusted
production identities.

## Test layers and independence

Keep three layers separate:

1. **Parsing and schema:** operate on literal bytes, no trusted launcher needed.
   Compare to fixed, externally specified expected values/errors rather than
   constructing expected results with the implementation's own serializer or
   hashing helper.
2. **Identity and policy:** use explicitly configured trust policies and real
   digests of small test artifacts. A syntactically valid manifest is not
   automatically trusted. Controlled fake image verifiers can exercise error
   propagation, but cannot demonstrate actual OCI verification or isolation.
3. **Integration and isolation:** run on the supported container runtime with
   real, locally built OCI images, controlled source snapshots, and a separately
   trusted launcher. Verify behavior at the external interface. Mocks alone
   cannot establish digest verification, mount restrictions or TOCTOU safety.

Compare decisions and required failure categories; exact human-readable error
messages are not part of this contract. Failures must not execute the planner,
fall back to host Python, or produce a successful result. Tests involving
sidecar, snapshots and execution gate belong to those later stages and must not
be represented as passing before those components exist. Resource limits and
platform-specific execution capabilities must be documented; unsupported
platforms should skip integration tests with an explicit reason, not report them
as successful security verification.

## Fixed byte fixture

The repository file `tests/fixtures/planner/manifest-valid.json` is UTF-8 JSON,
with LF line endings and a final newline. Its SHA-256 is:

```
8475dde84635714b169244497c7bf74f74f1e57b102199b64bc52dfac58b23c5
```

The expected exact ID is:

```
mashup-lab-timing/0.1/sha256:8475dde84635714b169244497c7bf74f74f1e57b102199b64bc52dfac58b23c5
```

It is a **schema and byte-identity fixture only**. The image, Python and wheel
hashes are fabricated repeated digits; no image is supplied, approved or
claimed to be runnable. Expected result: schema and digest identification
succeed; admission under an empty trust policy fails. Tests must read the
committed raw bytes, check the pinned expected hash/ID above independently, and
must not rewrite, parse-and-reserialize, or normalize newlines before hashing.
On any platform where a checkout transforms the bytes, this fixture must fail
rather than silently adapting its expected hash. A `.gitattributes` rule fixes LF
in the Git checkout. Fixture changes require an explicit review and new pinned
expected digest.

## Parsing, shape and exact-byte identity vectors

Each mutation below starts from the fixed fixture unless otherwise stated.

| Case | Input / operation | Required outcome |
| --- | --- | --- |
| Valid object | Original fixture bytes | Accept as schema v0.1; extract the exact ID above. No admission claim. |
| Whitespace | Append one ASCII space after the final newline | JSON values remain valid; SHA-256 and ID differ; reject when checked against the original ID. Do not change the expected ID. |
| Object order | Reverse top-level member order, leave values intact | Schema may accept; original byte ID must fail. No canonicalization. |
| Duplicate key | Insert another `"manifest_version"` in the same object, even with the same value | Reject; likewise duplicate nested keys. |
| Malformed bytes | Invalid UTF-8, truncated JSON, or trailing non-whitespace | Reject before trusting any fields. |
| Invalid JSON constants | Use `NaN` or `Infinity` anywhere | Reject; do not accept parser-specific extensions. |
| Shape | Remove a required field, set it to `null` where not nullable, or add an unknown field at any object level | Reject. Explicit `null` is allowed only for `git_commit` and `git_dirty`. |
| Types | Set `git_dirty` to `1` or `"false"`; use non-array `entrypoint`; use an empty entrypoint | Reject; booleans are not numbers and a shell string is not an argv list. |
| Unsupported semantics | Set manifest version, implementation, contract, or isolation policy to an unsupported value | Reject rather than silently downgrading. |
| IDs and digests | Use uppercase, wrong length, non-hex, missing `sha256:` on fields that require it, or mismatched contract/digest in `planner_id` | Reject. The ID uses a bare digest after its `sha256:` prefix. |
| Paths | Use a relative path, a `..` component or a non-normalized path for an image artifact | Reject. Existence and regular-file status are verified against the image at admission, not by JSON schema alone. |
| Dependency list | Duplicate a normalized dependency name or reorder two otherwise valid dependency records out of name order | Reject. Do not infer acceptance from a Python dict silently overwriting duplicates. |
| Git provenance | `git_commit: null` and `git_dirty: null` as in fixture | Schema accepts; neither field grants trust. A dirty or unknown tree must not be reported as clean. |

For a whitespace or reordered-key case, also test that recomputing its *new*
digest produces a different candidate ID. It remains untrusted until a local
policy explicitly approves that exact ID and image; merely updating a sidecar
must not add trust.

See also the [trust and execution contract](planner-trust-and-execution-specification.md)
for policy decisions and explicit PASS/FAIL/UNAVAILABLE semantics.

## Policy, build and invocation vectors

For the following cases, fixture hash constants are not OCI images. Integration
tests must instead construct small actual single-platform OCI images, calculate
and independently record their OCI manifest/config/layer digests, and explicitly
install and remove test-only policy entries. The approved artifact must not be
pulled from a mutable tag during the test. Test order must not affect policy.

| Setup / operation | Required outcome |
| --- | --- |
| Valid manifest and image, exact ID explicitly approved, matching contract/platform and compliant invocation | Admit for recomputation; verify the actual invocation uses the approved image and entrypoint. |
| Valid manifest and image but unknown or revoked ID | Deny without starting planner, even if the sidecar supplies the manifest. |
| Approved manifest but mismatched image manifest/config/layer bytes or missing blob | Deny; no fallback to image tag or host Python. |
| Approved image but interpreter or dependency artifact missing, non-regular, altered, or inconsistent with manifest metadata | Deny. Manifest fields alone do not count as measurement. |
| `linux/amd64` manifest on incompatible platform, or a multi-platform index supplied instead of its approved single-platform manifest | Deny before planner execution. |
| Forged planner process prints an approved ID but was not launched from the approved image | Deny; printed claims are not attestation. |
| Sidecar changes to another well-formed unapproved ID or requests a remote executable | Deny; it cannot mutate policy or choose code. |
| Manifest build label or Git fields are changed, then a matching new manifest hash is supplied | New identity is unapproved until separately allowed; the label or commit is not trust evidence. |

## Isolation and snapshot integration vectors

These require an actual supported launcher and image. An untrusted test planner
or helper inside the controlled image should attempt each forbidden action;
observe the result externally, not only a log line printed by that process.

- Network connection and writes to image root fail. Any writable output mount is
  separate and cannot override code, interpreter, libraries or import paths.
- Poisoned `PYTHONPATH`, `PYTHONHOME`, user site, startup hooks and preload
  variables do not cause attacker code to run. Host mounts or writable paths
  shadowing code/libraries are rejected, not silently accepted.
- Attempt replacement and in-place modification of project, plan and source
  paths during verification/copy and after verification. An execution may use
  only private snapshots whose own hashes and metadata were verified. It must
  fail on mismatches; the renderer must never consume subsequently replaced
  path contents. Metadata checks alone cannot prove an atomic original snapshot.
- A valid, trusted planner recomputes geometry from verified project snapshots;
  a self-consistent but forged plan with a matching updated plan-byte hash is
  rejected on full semantic comparison. This is a binding integration test,
  not a manifest-schema test.
- Failures and retries: a resource failure creates no successful render record;
  a retry revalidates fresh snapshots and policy. Environment/profile mismatch
  blocks execution under that profile without relabelling the timing as stale.

This test contract does not prove authenticity, safety on a compromised host,
reproducible builds, musical quality or audio bit identity. Those are separate
claims with separate prerequisites.
