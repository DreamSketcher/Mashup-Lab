# GitHub Actions Linux policy research

Status: **GitHub-hosted primitive probes run via a temporary branch push trigger**.
Neither the probes nor any hypothetical success implement a trusted policy
snapshot, authorize execution, or change the public `UNAVAILABLE` scaffold.
The candidate P1 profile in [platform research](linux-policy-snapshot-platform-research.md)
remains unverified. This document describes intended behavior, not test results.

## Workflow and evidence

`.github/workflows/linux-policy-research.yml` is manual-only
(`workflow_dispatch`), uses `ubuntu-24.04`, read-only repository token
permissions and no repository secrets. Checkout does not persist credentials.
The job collects the existing read-only P1 environment report and full
mountinfo. It records the running kernel and exact installed kernel package;
`required_kernel` is PASS only when `uname -r` is `6.8.0-31-generic` **and**
the installed package version is `6.8.0-31.31`. A different or unverifiable
kernel is UNAVAILABLE, not P1 success. Runner image/kernel revisions can change.

A private temporary 64 MiB loop image under a dedicated `/tmp` directory is
formatted ext4 and mounted with
`nodev,nosuid,noexec`, if noninteractive sudo, tools, loop allocation and mount
succeed. Only this throwaway mount is used for probes; no system directories,
accounts, policies or host filesystems are modified. If creation fails, each
probe reports UNAVAILABLE and is not run. Teardown unmounts and detaches only
the loop it allocated; on failure it records FAIL and does not recursively delete
a still-mounted tree. The workflow runs only on a GitHub-hosted disposable VM,
not a self-hosted host. Its use of sudo, losetup, mount and mkfs is privileged;
review the workflow before execution. GitHub documents the runner lifecycle and
passwordless sudo in its [hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

Each probe runs in a separate process with a 60-second deadline. Evidence includes
`status.tsv` (PASS/FAIL/UNAVAILABLE), per-probe stdout/stderr logs, raw loop
operations, kernel query, diagnostic collector output and unmodified mountinfo.
`environment` PASS means the collector ran, not that every environment check
succeeded. The `cleanup` status is appended at exit. The workflow uploads the
artifact even on a probe failure. A probe FAIL or failed teardown causes the job
to fail; unavailable probes are explicitly recorded and do not pretend to pass.
Timeouts are UNAVAILABLE. Artifact logs may contain host/namespace information;
review before redistribution. Upload failures, cancellation before upload or an
abrupt runner termination may leave no artifact and must not be read as PASS.

Probes cover: constrained `openat2` regular/symlink/escape behavior; a finite
concurrent intermediate-directory/symlink replacement race; a POSIX ACL read vs
write check using existing numeric UID 65534 via sudo; sealed memfd write,
resize and writable-mmap rejection; and competing flock processes including
lock-path replacement and a killed holder. A lock replacement being separately
lockable is an expected demonstration of the hazard, **not** lock protection.
The tests use only a finite set of operations and do not prove absence of races,
secure path bootstrap, ACL completeness, stable mount topology, snapshot source
coherence, updater coordination, recovery, or execution isolation. A successful
runner test is not a full P1 PASS. Missing utilities, privileges, isolation or
insufficient race observation are UNAVAILABLE where detected.

## Run and current blocker

GitHub documents that `workflow_dispatch` is usable only when the workflow file
exists on the repository's default branch: [events reference](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch).
This session may only push its Arena branch, so the workflow cannot become
registered on `main` from this session without an authorized merge. The attempted
`gh workflow run` returned HTTP 404; the [raw dispatch record](evidence/github-actions/dispatch-unavailable.txt)
contains the command and result. That dispatch created no Actions artifact. A subsequent push-triggered run
is described below; manual dispatch remains blocked until the workflow exists on
the default branch. Once it is
available on the default branch, an authorized operator can run:

```sh
gh workflow run linux-policy-research.yml --ref arena/32514431-mashup-lab
gh run list --workflow linux-policy-research.yml
gh run view RUN_ID --log
gh run download RUN_ID -D ./policy-research-evidence
```

`RUN_ID` above is explanatory and must be replaced by an actual run ID. Inspect
`status.tsv`, all logs, workflow conclusion, runner image and actual package
versions before drawing conclusions. The artifact is retained for 14 days, not
permanent storage. Treat the annotations and uninspected artifact as different levels of evidence;
only directly observed results may be asserted. Further blockers include
unavailable loop devices/sudo/ACL utilities, runner kernel drift and insufficient
privileges; the job reports these rather than installing packages or substituting
a host filesystem. P1 still requires the separately specified candidate VM,
precise image/mount/namespace/ACL conditions and independent platform tests.

## Observed branch run (not P1)

A one-off push-triggered run was used because manual dispatch was not registered
on `main`. Afterward the push trigger was removed; the workflow remains
manual-only. [Run 42539528762](https://github.com/DreamSketcher/Mashup-Lab/actions/runs/42539528762)
completed successfully on commit `6547752`. GitHub check annotations report:

| Check | Outcome |
| --- | --- |
| Running kernel | `7.0.0-1017-azure` |
| Exact candidate kernel/package | UNAVAILABLE |
| Environment collection | PASS (collector ran only) |
| Temporary loop ext4 and cleanup | PASS |
| openat2, path race, sealed memfd, flock | PASS for the limited primitive probes |
| ACL | UNAVAILABLE; no more specific reason available from annotations |

The green job permits UNAVAILABLE probes and is not a P1 or security pass. The
[API annotations](evidence/github-actions/run-42539528762/annotations.json) and
[run metadata](evidence/github-actions/run-42539528762/run.json) are preserved.
The workflow reported artifact upload success, but downloading it in this sandbox
failed because the redirected artifact storage host is inaccessible here; the
raw probe logs, full environment and specific ACL cause have **not** been
reviewed. An authorized user can inspect/download the artifact from the run page.
The exact requested VM/kernel and P1-B adapter acceptance remain UNAVAILABLE.

## ACL follow-up run

In the earlier run, the user reported `UNAVAILABLE: uid 65534 cannot traverse
temporary directory` in the downloaded artifact. That indicated the probe did
not reach ACL evaluation; it did not demonstrate missing ACL support. The
harness now creates its dedicated parent under `/tmp` with traversal allowed,
without changing `/tmp` or other system directory permissions. Its image file
and mount remain in that temporary directory, and cleanup still unmounts and
detaches the allocated loop device.

[Run 42539860170](https://github.com/DreamSketcher/Mashup-Lab/actions/runs/42539860170)
on commit `550fd5a` reports `PASS` for separate `acl_user`, `acl_group` and
`acl_default` probes. They test UID 65534 read then write for a named user ACL,
named group ACL write then denial via the ACL mask, and an inherited default ACL
on a newly created file. The same run reports PASS for loop setup and cleanup,
openat2, path race, memfd and flock; the kernel is `7.0.0-1017-azure`, and the
exact required kernel remains UNAVAILABLE. These are finite primitive probes,
not trusted policy evaluation. [Run metadata](evidence/github-actions/run-42539860170/run.json)
and [annotations](evidence/github-actions/run-42539860170/annotations.json) are
available. Full raw logs were uploaded as a GitHub artifact but cannot be
downloaded from this network-restricted sandbox, so this account relies on the
reported annotations rather than an independent review of the raw ACL logs.

Intermediate symlink/hardlink and mount topology coverage, independent
reader/updater coordination, protected lock replacement tests and the exact
candidate VM remain open. The original P1-B adapter acceptance scenarios remain
NOT_RUN. Workflow push triggers used for these experiments have been removed;
manual dispatch still requires the workflow on the default branch.
