#!/usr/bin/env bash
# Read-only environmental evidence collector; does not assess trust or create a VM.
# Usage: collect-linux-p1.sh OUTPUT_DIRECTORY [UNPRIVILEGED_USER]
set -u
# Include standard administrative binary directories even when run unprivileged.
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "usage: $0 OUTPUT_DIRECTORY [UNPRIVILEGED_USER]" >&2
    exit 2
fi
out=$1
negative_user=${2:-mashup-p1-unprivileged}
if [ -e "$out" ]; then
    echo "output directory already exists: $out" >&2
    exit 2
fi
if ! mkdir -m 700 -p -- "$out"; then
    echo 'cannot create output directory' >&2
    exit 2
fi
# A failed collection operation is recorded, never replaced with an inferred value.
log="$out/diagnostics.txt"
exec > "$log" 2>&1
printf 'P1 read-only collector v1; no compliance or admission decision\n'
printf 'negative-test username: %s\n' "$negative_user"
run() {
    printf '\n=== '
    printf '%q ' "$@"
    printf '===\n'
    if command -v -- "$1" >/dev/null 2>&1; then
        "$@"
        rc=$?
    else
        printf 'UNAVAILABLE: command not installed: %s\n' "$1"
        rc=127
    fi
    printf '[exit=%s]\n' "$rc"
}
run date -u +%Y-%m-%dT%H:%M:%SZ
run uname -a
run cat /etc/os-release
run id
run readlink /proc/$$/ns/user
run readlink /proc/$$/ns/mnt
run readlink /proc/1/ns/user
run readlink /proc/1/ns/mnt
run cat /proc/$$/uid_map
run cat /proc/$$/gid_map
run cat /proc/$$/status
run systemd-detect-virt
run ps -p 1 -o pid=,comm=,args=
run lsns -t user
run lsns -t mnt
run systemctl --version
run getent passwd "$negative_user"
run id "$negative_user"
run dpkg-query -W -f='${Package}\t${Version}\t${Status}\n' 'linux-image-*' systemd e2fsprogs util-linux acl
run findmnt -T / -o TARGET,SOURCE,FSTYPE,OPTIONS,PROPAGATION
run stat -f -c 'filesystem_type=%T magic=%t' /
for path in / /etc /etc/mashup-lab /etc/mashup-lab/policy.json /etc/mashup-lab/policy.lock; do
    run stat -c 'path=%n type=%F uid=%u gid=%g mode=%a links=%h device=%d inode=%i' -- "$path"
    run getfacl -p -- "$path"
done
for command in qemu-system-x86_64 qemu-img virsh VBoxManage multipass cloud-localds getfacl setfacl capsh tune2fs; do
    printf '\n=== command -v %s ===\n' "$command"
    if command -v "$command"; then printf '[exit=0]\n'; else printf '[exit=1]\n'; fi
done
run ls -l /dev/kvm /dev/net/tun
run capsh --print
# Keep mountinfo in a separate, unmodified byte-for-byte file for later inspection.
printf '\n=== raw mountinfo ===\n'
if cat /proc/$$/mountinfo > "$out/mountinfo.txt"; then
    printf 'saved mountinfo.txt [exit=0]\n'
else
    rc=$?
    printf 'UNAVAILABLE: mountinfo read failed [exit=%s]\n' "$rc"
fi
# The caller may supply a real block device via environment only for this
# diagnostic, never for authorization. Do not guess a device from a mount name.
if [ -n "${P1_EXT4_DEVICE:-}" ]; then
    run tune2fs -l "$P1_EXT4_DEVICE"
else
    printf '\n=== ext4 superblock ===\nUNAVAILABLE: P1_EXT4_DEVICE not specified; no device guessed\n'
fi
printf '\nCollection finished. Command failures and unavailable facts are preserved above.\n'
