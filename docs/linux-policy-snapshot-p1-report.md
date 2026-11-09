# P1 report: candidate VM unavailable

Result: **UNAVAILABLE — P1 on the specified candidate was not run.** No VM was
created or is being claimed as available. This report records a read-only
preflight of the existing Arena workspace, which is **not** the requested VM.
No path-resolution, ACL-adversary, snapshot, flock, launcher or audio experiment
was performed. The existing snapshot API remains `UNAVAILABLE`.

## Why preparation stopped

The workspace has no `qemu-system-x86_64`, `qemu-img`, `virsh`, VirtualBox,
Multipass or cloud image tools on the collector's standard PATH; `/dev/kvm` is
absent. Absence of `/dev/kvm` alone does not exclude software emulation, but no
usable VM launcher is installed. A search in `/home/user`, `/opt`, and `/var/tmp`
(up to three levels) found no Ubuntu 24.04 image, qcow2, ISO or requested kernel
package; it is not a search of the whole host and does not prove none exists
elsewhere. Network access in this environment is restricted to a short allowlist
that does not include the official Ubuntu image/package hosts. No candidate
image or kernel artifact was obtained, so provenance and exact package version
could not be established. We did not attempt to install a substitute, alter the
host, create users, mount filesystems, or relabel the current machine as the VM.

To proceed requires an explicitly provisioned disposable Ubuntu Server 24.04
amd64 VM with the exact `6.8.0-31-generic` / `6.8.0-31.31` kernel package and
verified image provenance, or a permitted source and a working VM backend. The
historical kernel is for isolated testing only, not a production recommendation.
The candidate profile's image digest, mkfs features, storage model and full
mount options also need to be pinned and checked before a reproducible P1 PASS.

## Artifacts and reproducibility

- Collector: [`scripts/collect-linux-p1.sh`](../scripts/collect-linux-p1.sh).
  Run **inside the candidate VM** after trusted provisioning:

  ```sh
  sudo env P1_EXT4_DEVICE=/dev/REPLACE_WITH_VERIFIED_DEVICE \
    bash scripts/collect-linux-p1.sh /secure/new-output-dir p1-test-user
  ```

  Replace the device, output path and username with verified local values; do
  not run this example unchanged. The script is read-only with respect to system
  configuration but creates a new output directory and files. It records each
  command and exit code, full `/proc/<collector-pid>/mountinfo` in a separate
  file, namespaces, mappings, process capabilities, package information,
  ext4-related facts, ACL and `stat` output. `tune2fs` is attempted only when a
  device is explicitly supplied; it is not inferred from `findmnt`. The script
  does **not** create a VM or test isolation, validate effective ACLs, prove a
  namespace initial, verify artifact hashes, or issue a profile PASS. It is not a
  trusted policy loader. Failures and missing commands are recorded; completion
  of the collector is not completion of P1. Output can contain host paths and
  user/namespace information; review before sharing. Use a fresh output path:
  the collector refuses an existing one.
- Workspace preflight output: [diagnostics.txt](evidence/p1-sandbox-unavailable/diagnostics.txt)
  and raw [mountinfo.txt](evidence/p1-sandbox-unavailable/mountinfo.txt).
  These contain collector output from the **wrong environment**, not VM evidence.
  The workspace clock recorded `2026-11-09T00:06:59Z` in the raw log.
- SHA-256 of captured files (byte integrity only, not a security attestation):

  ```text
  diagnostics.txt  a03efeaafd099e624a5fbfac00e00da3e6a5f9537db1a8cacbac17665bd49bc7
  mountinfo.txt    6ba1f449348504183653fcdc1d3341f61d125ba6fe97330ab4bbf85df4f9e1d2
  collector        e8482ab7e5cda491339e899077f88d29e897df935559b71cba0255877b46cc1e
  ```

The separate mountinfo is copied verbatim from the collector process's proc
entry. It is a point-in-time view, not evidence that topology stayed unchanged.
The collector's package listing may return a nonzero status if a glob or package
is absent; output and exit code are retained. A tool present on PATH does not
establish permissions or the security of its results.

## Observed preflight and differences

| Candidate requirement | Actual workspace observation | Result for candidate |
| --- | --- | --- |
| Ubuntu Server 24.04 amd64 | Debian GNU/Linux 12; `uname` reports x86_64 | UNAVAILABLE: wrong distribution; architecture alone matches. |
| `6.8.0-31-generic`, package `6.8.0-31.31` | Running kernel `6.1.158+`; `dpkg-query` found no `linux-image-*` packages | UNAVAILABLE: wrong running kernel and no requested package evidence. |
| Local ext4 root, `rw,relatime`, ext4 `errors=remount-ro`, known features | `findmnt`: `/dev/vda`, ext4, `rw,relatime,discard`, propagation `shared`; mountinfo reports ext4 superblock `rw,discard`. No block device was supplied for `tune2fs`. | UNAVAILABLE: options differ, complete superblock features and storage provenance unverified. |
| systemd services in same initial mount namespace, recursively private | PID 1 is `systemd`; `systemd-detect-virt` reports `kvm`. Collector mount namespace `mnt:[4026531841]`, root propagation `shared`. No candidate loader/updater services exist. | UNAVAILABLE: baseline requires private propagation and verified service namespace relationship. |
| initial user namespace and privileged model | Collector user namespace `user:[4026531837]`, UID/GID maps start `0 0 4294967295`; reads of PID 1 namespace links failed. Collector UID/GID 1001, effective/permitted capabilities zero; bounding set recorded. | UNAVAILABLE: mappings and inode label alone do not independently establish the whole target threat model or service privileges. |
| separate unprivileged negative-test user | Requested `mashup-p1-unprivileged` not found by `getent`/`id`. Existing collector user belongs to group `sudo`. | UNAVAILABLE: no specified isolated negative-test principal was provisioned or verified. |
| root-owned protected policy path, POSIX access/default ACLs | `/` and `/etc` stat as root-owned mode 755; `/etc/mashup-lab` and policy/lock paths do not exist. `getfacl`/`setfacl` are unavailable. | UNAVAILABLE: path and actual ACL checks cannot be performed; mode alone is not sufficient. |
| VM image and exact package provenance | No candidate artifacts or hashes obtained | UNAVAILABLE. |

A `FAIL` would denote an observed violation during a valid P1 evaluation; here
several workspace facts plainly differ from the proposed target, but there is no
candidate VM to evaluate. They are discrepancies and blockers, not a failed
security test of an actual candidate.

## Decision

**Do not use this workspace for subsequent candidate-profile experiments.**
P1 is UNAVAILABLE, and the process stops here. The raw evidence supports only
what it actually reports. Once a matching disposable VM and complete artifact
provenance are available, rerun the collector inside it, independently review
all results (including ACL/mount security), and only then decide whether P1
passes. Successful collection alone is not that decision.
