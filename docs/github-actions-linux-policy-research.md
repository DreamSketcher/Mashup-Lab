# GitHub Actions Linux policy research

Status: **workflow prepared; dispatch attempted, no GitHub-hosted run observed**.
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

A private temporary 64 MiB loop image is formatted ext4 and mounted with
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
contains the command and result. The actual runner environment, exact kernel and
all individual experiment outcomes are therefore **UNAVAILABLE**, not PASS or
FAIL, and no Actions artifact was created. Once it is
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
permanent storage. No GitHub runner measurements or results are asserted until an
actual run completes and its artifacts are examined. Further blockers include
unavailable loop devices/sudo/ACL utilities, runner kernel drift and insufficient
privileges; the job reports these rather than installing packages or substituting
a host filesystem. P1 still requires the separately specified candidate VM,
precise image/mount/namespace/ACL conditions and independent platform tests.
