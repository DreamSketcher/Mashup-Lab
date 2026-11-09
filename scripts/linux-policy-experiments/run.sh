#!/usr/bin/env bash
# Disposable GitHub-hosted runner only. Never modifies host system directories.
set -uo pipefail
if [ $# -ne 1 ]; then echo 'usage: run.sh NEW_ARTIFACT_DIRECTORY' >&2; exit 2; fi
out=$1
mkdir -p "$out"
: > "$out/status.tsv"
echo -e 'probe\tstatus\tdetail' >> "$out/status.tsv"
status() { printf '%s\t%s\t%s\n' "$1" "$2" "$3" >> "$out/status.tsv"; }
# /tmp is traversable by the test UID; no system directory permissions change.
root=$(mktemp -d /tmp/mashup-policy-probes.XXXXXXXX) || exit 2
chmod 755 "$root"
loop=''
mounted=0
cleanup() {
    # Never recursively delete a directory while our filesystem remains mounted.
    if [ "$mounted" = 1 ]; then
        if sudo -n umount "$root/mount" >> "$out/loop.log" 2>&1; then mounted=0
        else echo 'FAIL: unmount failed; loop retained' >> "$out/loop.log"; status cleanup FAIL umount; return 1; fi
    fi
    if [ -n "$loop" ]; then
        if ! sudo -n losetup -d "$loop" >> "$out/loop.log" 2>&1; then
            echo 'FAIL: detach failed; directory retained' >> "$out/loop.log"; status cleanup FAIL detach; return 1
        fi
    fi
    rm -rf -- "$root"
    status cleanup PASS 'temporary filesystem unmounted and loop detached when applicable'
}
trap 'rc=$?; trap - EXIT; cleanup || rc=1; exit "$rc"' EXIT
bash scripts/collect-linux-p1.sh "$out/environment" > "$out/collector.log" 2>&1
collector_rc=$?
if [ "$collector_rc" -eq 0 ] && [ -f "$out/environment/mountinfo.txt" ]; then
    status environment PASS 'collector ran; inspect raw exit codes; not profile PASS'
else
    status environment UNAVAILABLE "collector exit=$collector_rc"
fi
{
    printf 'running kernel: '; uname -r
    printf 'kernel package query:\n'; dpkg-query -W -f='${Package} ${Version} ${Status}\n' 'linux-image-6.8.0-31-generic' 2>&1 || true
} > "$out/kernel.log" 2>&1
if [ "$(uname -r)" = '6.8.0-31-generic' ] && dpkg-query -W -f='${Version} ${Status}' linux-image-6.8.0-31-generic 2>/dev/null | grep -qx '6.8.0-31.31 install ok installed'; then
    status required_kernel PASS 'running kernel and package match; not full P1'
else
    status required_kernel UNAVAILABLE 'exact running kernel/package not established; see kernel.log'
fi
{
    echo 'loop tools and privileges:'
    command -v losetup; command -v mkfs.ext4; command -v mount; command -v sudo
    sudo -n true
    ls -l /dev/loop-control /dev/loop* 2>&1 || true
} > "$out/loop.log" 2>&1
loop_ready=0
if command -v sudo >/dev/null && sudo -n true >/dev/null 2>&1 && command -v losetup >/dev/null && command -v mkfs.ext4 >/dev/null && command -v mount >/dev/null; then
    mkdir "$root/mount"
    if truncate -s 64M "$root/disk.img" >> "$out/loop.log" 2>&1; then
        loop=$(sudo -n losetup --find --show "$root/disk.img" 2>> "$out/loop.log") || loop=''
        if [ -n "$loop" ]; then
            echo "allocated $loop" >> "$out/loop.log"
            if sudo -n mkfs.ext4 -F "$loop" >> "$out/loop.log" 2>&1 && sudo -n mount -t ext4 -o nodev,nosuid,noexec "$loop" "$root/mount" >> "$out/loop.log" 2>&1; then
                mounted=1
                if sudo -n chown "$(id -u):$(id -g)" "$root/mount" >> "$out/loop.log" 2>&1 && chmod 755 "$root/mount"; then
                    loop_ready=1
                    findmnt -T "$root/mount" -o TARGET,SOURCE,FSTYPE,OPTIONS,PROPAGATION >> "$out/loop.log" 2>&1
                fi
            fi
        fi
    fi
fi
if [ "$loop_ready" = 1 ]; then
    status loop_ext4 PASS 'temporary filesystem mounted; see loop.log'
else
    status loop_ext4 UNAVAILABLE 'cannot create/mount isolated ext4; see loop.log'
fi
any_fail=0
for probe in openat2 path_race acl_user acl_group acl_default memfd flock; do
    if [ "$loop_ready" != 1 ]; then
        echo 'UNAVAILABLE: isolated ext4 not available; probe not run' > "$out/$probe.log"
        status "$probe" UNAVAILABLE 'loop filesystem unavailable'
        continue
    fi
    PROBE_ROOT="$root/mount" timeout 60s python3 scripts/linux-policy-experiments/probes.py "$probe" > "$out/$probe.log" 2>&1
    rc=$?
    case "$rc" in
        0) status "$probe" PASS 'behavioral probe only, not security approval' ;;
        77) status "$probe" UNAVAILABLE 'missing prerequisite or insufficient observation' ;;
        124) status "$probe" UNAVAILABLE 'probe timed out' ;;
        *) status "$probe" FAIL "exit=$rc; see $probe.log"; any_fail=1 ;;
    esac
done
if [ "$any_fail" = 1 ]; then exit 1; fi
