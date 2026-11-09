# Policy anti-rollback and durable completion — draft v0.1

> **Scope update:** This document is optional trusted-execution research, not a
> prerequisite for the Mashup Lab music MVP. For current priorities and the
> simpler render-time binding direction, see [MVP scope](mvp-scope.md). Historical
> references to “MVP” below apply only to the proposed trust subsystem.

Status: **design proposal only**. No trusted generation authority, policy
updater, recovery gate, admission mechanism or Linux snapshot loader is
implemented. `capture_policy_snapshot()` remains `UNAVAILABLE`. This document
complements the [crash-consistency test contract](linux-policy-crash-consistency-test-contract.md),
[trusted policy loading](trusted-policy-loading-specification.md) and
[launcher lifecycle](planner-launcher-lifecycle-specification.md) drafts. It
proposes a future protocol; it does not establish any filesystem, authority,
VM or production security guarantee.

## Problem and threat boundary

A locally valid policy can be stale. Atomic `rename` and file/directory `fsync`
may establish publication durability under a stated storage model, but neither
proves which policy version was previously acknowledged. Rolling back an entire
VM or disk snapshot can roll back **both** policy and local completion record.
A hash in the same rollbackable storage does not detect this. This is distinct
from accidental torn writes and from trusted operator actions.

Proposed anti-rollback assumes an independently trusted generation authority
outside the rollback domain, a protected launcher/updater/installation, a kernel
and storage stack satisfying their stated contracts, and a trusted operator.
An attacker may replace or restore local disk snapshots, replay old policy bytes
or corrupt local files; the authority's durable state and authenticated channel
must not be rollbackable or forgeable by that attacker. Compromise of the
operator, authority, its credentials, launcher, kernel or privileged host is
outside this model. There is no claim that an arbitrary untrusted privileged
process can be excluded with Unix permissions alone.

## What is being protected

- **Publication identity:** exact policy file bytes, identified by SHA-256 and a
  monotonically increasing generation. File hashes identify bytes, not authors.
- **Durable completion:** a publication is acknowledged only after the required
  local persistence steps and the authority's atomic durable commit succeed.
- **Admission binding:** the future gate compares the exact protected snapshot
  bytes it will use with a fresh authoritative generation/digest and holds the
  coordination lock through its admission point.
- **Anti-rollback:** restoring old local storage must not cause an older
  generation/digest to be silently admitted while the authority retains a newer
  committed record. Authorized operators could intentionally publish earlier
  *contents* again as a new generation; monotonic generations alone do not
  prevent that administrative choice.

A policy's schema and trust still require separate validation. SHA-256 provides
integrity comparison subject to collision resistance, not signature-based
provenance or proof that a particular historical program ran.

## Candidate authority contract — no backend selected

For each installation identity, the authority holds a durable record
`(generation, policy_sha256)`. Generation is a nonnegative integer, digest is
SHA-256 of the exact policy bytes, including whitespace and line endings. Its
operations must have these properties:

1. `read_current`: authenticated, fresh/linearizable read of the current record,
   not a cached or replayable historical response. It distinguishes absence,
   unavailability and integrity/authentication errors.
2. `commit(expected, new)`: authenticated, atomic compare-and-set against the
   exact current record, accepting only generation `expected.generation + 1` and
   a valid digest. A confirmed success means the new record is durable across
   the authority's stated failures and later reads cannot return a prior record.
   A conflict does not commit the request. Timeouts or transport failures have an
   **unknown** outcome unless reconciled by a fresh authenticated read.
3. Records cannot be rewritten backwards, deleted, reset or replayed by a local
   VM/disk rollback or by an untrusted client. Authenticate both caller and
   authority and bind messages to this installation identity. If these
   properties cannot be established, anti-rollback is UNAVAILABLE.

This is a required abstraction, **not an assertion that an existing service,
TPM, counter, filesystem, or hardware implementation meets it**. Selection,
authentication, replay protection, persistence, atomicity, high availability,
key protection and recovery are unresolved. A hardware monotonic counter alone
contains no digest and does not automatically implement the atomic pair above.
Sequence numbers stored only on the same disk or supplied by the sidecar do not
satisfy this contract. Independent audit/signatures may be useful, but need
separate trust and key-management design.

## Bootstrap and single-host serialization

Initial authority enrollment is a privileged, out-of-band operation: provision
and verify the exact initial policy bytes and record `(0, SHA-256(bytes))` by a
trusted procedure, then protect the authority identity and credentials. No
trust-on-first-use, automatic reset, deletion or re-enrollment is allowed merely
because local files, a VM snapshot or the authority are missing. Loss of
credentials, missing record, or contradictory bootstrap state means
UNAVAILABLE until a separately specified audited operator recovery procedure is
performed. Authority migration, key rotation, decommissioning, generation
exhaustion and disaster recovery remain open.

The following MVP model is **single-host**: updater, recovery and admission gate
are trusted cooperating participants that use the same protected lock inode,
held from fresh authority read through their respective commit/admission point.
The lock and path authority must satisfy the trusted policy-loading contract;
`flock` alone is advisory and does not defend its pathname or against
non-cooperating writers. Multi-host/distributed serialization and resistance to
split brain are not specified. If the required lock, stable identity, authority
or trusted snapshots cannot be established, operations fail closed.

## Candidate publication protocol

Let `R = (g, h_old)` be the freshly read authority record. Under the protected
exclusive lock:

1. Verify that the currently installed protected policy snapshot hashes to
   `h_old`, validate its schema/authority and ensure no unresolved recovery or
   prior update exists. If not, stop; never overwrite ambiguity with a new
   "success". Construct and validate `new` policy bytes; compute `h_new` from
   those exact bytes. Generation `g + 1` is a record property, not an implicit
   policy-file field; same bytes under a later generation are possible.
2. Write the full new bytes to a safely created private temporary file in the
   protected policy directory, validate/hash that file, `fsync` it, rename it
   atomically over the policy path, and `fsync` the parent directory. Each
   operation must succeed; source/snapshot and trusted path checks still apply.
   On any error or uncertain local outcome, do not commit or acknowledge; enter
   recovery with admission blocked.
3. Call `commit(R, (g + 1, h_new))`. **The authority's durable atomic commit is
   the publication linearization point**, not `rename` alone. Only after a
   confirmed successful commit may the updater report publication completed.
   Record an audit receipt identifying installation, old/new records and outcome;
   the authoritative tuple, not a local receipt, is the anti-rollback anchor.
   Persistence and exact schema for the audit receipt remain to be designed.
4. Release the lock only after outcome is handled. If the response is lost or
   times out, do not guess and do not acknowledge. Reconcile using a fresh
   authenticated authority read and the exact local policy snapshot, under the
   lock, as in the recovery table. If the authority is unavailable or returns an
   unexpected record, keep admission blocked and report UNAVAILABLE.

CAS rejection due to a different current record is not an invitation to overwrite
it. Stop, reconcile, and require an explicit new update after recovery. A
cooperating reader must not observe the interval between rename and authority
commit as an admissible state: the updater holds the lock, and an updater crash
requires recovery before the next admission. An unprotected/non-cooperating
reader or writer is outside this protocol.

## Recovery and crash cases

After a crash, reboot, failed syscall or unknown response, obtain the protected
lock, read the authority freshly, and capture/validate the exact current policy
bytes via the future trusted snapshot mechanism. Do not use a stale cached
record. Temporary files are not automatically promoted. Local state and
exclusive lock alone cannot prove authority state. In the following table,
`old = (g, h_old)` and `new = (g + 1, h_new)` refer to records of the interrupted
update; reconstructing the identity of that update must itself use reliable
protected information. If it is unavailable, use the generic equality rule and
do not invent the history.

| Observed authority | Observed local policy | Required behavior |
| --- | --- | --- |
| `old` | hash `h_old` | Locally consistent with old committed record. Old may be used only after all other recovery and trust checks pass; no claim the attempted update completed. |
| `old` | hash `h_new` | Uncommitted local publication. **Deny admission**; restore or reconcile only by an explicitly authorized, separately specified recovery procedure. Do not silently commit, accept new, or report update success. |
| `new` | hash `h_new` | Consistent with the committed record; validate authority, source snapshot and policy, then permit future admission checks. A lost response may be recorded as reconciled, not as proof of a previously delivered acknowledgement. |
| `new` | hash `h_old`, missing or different | Rollback, loss or corruption suspected. **Deny admission**; do not downgrade the authority. Recovery may require obtaining exact `h_new` bytes from a trusted source. |
| unknown/unavailable/unexpected | any | **UNAVAILABLE**, deny; no cache or last-known-good fallback. |

If the authority has advanced further than this attempted update, validate the
actual current `(generation, digest)` against the exact snapshot; do not infer
success or restore an older version. If `h_old == h_new`, the bytes alone cannot
distinguish the two generations; use the authority tuple and audit context, not
an assertion that equal hashes prove which update happened. Fresh authority
reads and monotonic ordering are required even for equal contents.

A crash before local rename normally leaves old bytes; after rename but before
directory fsync either old or new may survive under the tested storage model.
A crash after local fsync but before authority commit can leave `h_new` while
`R` is still old: this is intentionally a **fail-closed availability cost**.
After authority commit but before the updater receives a response, a fresh read
can identify a matching committed tuple; it cannot prove the operator saw a
success message. Treat confirmation and acknowledgement delivery as distinct.
A failed authority read or uncertain durability cannot be resolved from the
local file alone.

## Admission using the confirmed version

A future admission attempt must use one protected policy snapshot and the same
verified bytes for hashing, parsing and decision-making. Under the protected
shared coordination lock, perform a fresh authenticated authority read and
require its digest to equal the snapshot digest. Validate policy schema,
installation authority and all other trust/execution prerequisites. Record the
exact `(generation, digest)`, policy snapshot hash and decision using a trusted
recording mechanism, then reach the defined admission point while the lock is
held. The exact decision-record format, durability and atomic relationship to
planner release are **not yet specified**; until they are, admission is
UNAVAILABLE. Never reopen the mutable policy pathname after checking it to make
the decision. `compare-policy` only compares an untrusted supplied file and is
not this gate.

The lock serializes cooperating local updates: an authority commit completed
before a new admission acquires its lock must be reflected by its fresh read;
an admission recorded before the updater commits may continue according to the
existing in-flight rule. This rule does not revoke already admitted work and
makes no claims for another host or out-of-protocol authority writers. If the
authority allows external writers that bypass the shared lock, this
single-host ordering guarantee is invalid and admission must remain UNAVAILABLE
until a distributed protocol is designed.

## Independent acceptance cases — NOT RUN

The following are future tests against real implementations and an explicitly
selected authority and disposable target VM. Fake authorities can exercise
control flow but cannot prove durability, freshness, authentication or
anti-rollback:

- Enroll a valid initial tuple and verify exact snapshot identity; missing,
  corrupted or replayed authority responses fail closed, never trust on first use.
- Interrupt at every local C0–C4 point from the crash contract, before/after the
  authority commit, and after a commit with its response deliberately lost.
  Compare exact local bytes, actual durable authority state, acknowledgements and
  gate decisions to the recovery table; unknown fault points are UNAVAILABLE.
- Restore a full older local VM/disk snapshot after a later revocation commit;
  a fresh external record must reject the stale policy. Restore both local disk
  and the authority together as a negative demonstration: an external anchor
  that rolls back too cannot provide the claimed guarantee.
- Test transport loss, authority restart, response replay, identity mismatch,
  CAS conflict, duplicate update requests and authority storage failure. No
  failure may silently fall back to an old policy or reset the generation.
- Race updater, recovery and admission using real locks, including lock path
  replacement attempts; verify same-byte snapshots and both orderings of a
  completed revocation relative to the admission point. A fake in-memory
  decision is not sufficient.
- Exercise equal-content/new-generation updates, missing or corrupt local files,
  unauthenticated policy substitution, power-fault simulation and authorized
  operator recovery. Record unsupported scenarios as UNAVAILABLE or NOT_RUN,
  not PASS.

**PASS** applies only to a specified case with all prerequisites and an
independently confirmed fault boundary; **FAIL** denotes an observed violated
invariant; **UNAVAILABLE** denotes an unestablished prerequisite or uncertain
outcome; **NOT_RUN** denotes unattempted/unimplemented cases. A test pass does
not establish safety against a compromised trust anchor or arbitrary platform.
Until authority, recovery and admission are designed, implemented and validated,
no anti-rollback or admission guarantee is claimed.
