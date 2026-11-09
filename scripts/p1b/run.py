#!/usr/bin/env python3
"""P1-B evidence runner; kernel probes are not trusted-adapter acceptance."""
import argparse
import datetime
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PROBES = ROOT / 'scripts/linux-policy-experiments/probes.py'

# IDs, expected outcomes and prerequisites are independent of probe execution.
PRIMITIVES = (
    ('P1B-01', 'openat2', 'beneath lookup succeeds; symlinks and escape are rejected', 'Linux x86-64, openat2'),
    ('P1B-02', 'path_race', 'concurrent symlink swaps never expose wrong content', 'Linux x86-64, openat2; both race outcomes observed'),
    ('P1B-03', 'acl', 'named ACL permits read and denies write for UID 65534', 'POSIX ACL utilities, sudo, existing UID 65534 and traversable test mount'),
    ('P1B-04', 'memfd', 'sealed content, size and writable shared mappings cannot be changed', 'Linux memfd and file seals'),
    ('P1B-05', 'flock', 'competitor blocks, replaced lock inode is distinct, killed sole owner releases lock', 'Linux flock and process creation'),
)
# These require actual future production interfaces, fixtures and acceptance oracles.
# Do not replace them with stubs that might pass without exercising the adapter.
PENDING = (
    ('P1B-06', 'trusted-chain', 'each parent ownership, modes and actual ACLs checked'),
    ('P1B-07', 'file-types', 'policy symlink, hardlink, FIFO, device and directory rejected safely'),
    ('P1B-08', 'acl-authority', 'named user/group ACL grants and default ACLs correctly evaluated'),
    ('P1B-09', 'path-escape', 'intermediate symlinks and traversal cannot escape trusted root'),
    ('P1B-10', 'snapshot-races', 'concurrent file/directory replacement and in-place writes never yield unchecked policy'),
    ('P1B-11', 'same-bytes', 'snapshot, hash, parser and consumer use identical protected bytes'),
    ('P1B-12', 'update-lock', 'reader and updater share protected lock through documented admission point'),
    ('P1B-13', 'updater-crash', 'crash around publication never admits partial policy'),
    ('P1B-14', 'fail-closed', 'missing ACL, invalid mount and syscall errors never cause authorization'),
    ('P1B-15', 'admission-revocation', 'revocation ordering obeys the admission-point contract'),
    ('P1B-16', 'policy-invariants', 'limits, malformed inputs, missing/revoked and identity mismatch do not fall back'),
    ('P1B-17', 'mount-topology', 'bind mounts, topology changes and unknown mount state fail closed'),
    ('P1B-18', 'lock-replacement', 'protected shared lock inode cannot be replaced to bypass coordination'),
)


def profile():
    """Cheap prerequisite check, NOT P1 validation or permission to execute."""
    try:
        os_release = Path('/etc/os-release').read_text(encoding='utf-8')
        version = subprocess.run(['dpkg-query', '-W', '-f=${Version} ${Status}',
                                  'linux-image-6.8.0-31-generic'], capture_output=True, text=True, timeout=10)
        return {'system': platform.system(), 'machine': platform.machine(),
                'kernel': platform.release(), 'os_release': os_release,
                'package_stdout': version.stdout, 'package_stderr': version.stderr,
                'package_exit': version.returncode}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'error': str(exc), 'system': platform.system(), 'machine': platform.machine(),
                'kernel': platform.release()}


def target_matches(info):
    lines = set(info.get('os_release', '').splitlines())
    return (info.get('system') == 'Linux' and info.get('machine') == 'x86_64'
            and info.get('kernel') == '6.8.0-31-generic'
            and 'ID=ubuntu' in lines and 'VERSION_ID="24.04"' in lines
            and info.get('package_exit') == 0
            and info.get('package_stdout') == '6.8.0-31.31 install ok installed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workdir', required=True, type=Path, help='empty disposable VM test filesystem, never a production directory')
    parser.add_argument('--output', required=True, type=Path, help='new report directory outside workdir')
    parser.add_argument('--ack-disposable', action='store_true', help='confirm VM and paths are disposable')
    args = parser.parse_args()
    if not args.ack_disposable:
        parser.error('explicit --ack-disposable is required')
    work = args.workdir.resolve(strict=True)
    if not work.is_dir() or any(work.iterdir()):
        parser.error('workdir must be an existing empty dedicated test directory')
    output = args.output.absolute()
    if output.exists() or output.resolve().is_relative_to(work) or work.is_relative_to(output.resolve()):
        parser.error('output must be new and separate from workdir')
    output.mkdir(parents=True, mode=0o700)
    info = profile()
    # Persist raw environment even on an unavailable target. No attempt is made
    # to install packages or modify system directories.
    try:
        result = subprocess.run(['bash', str(ROOT / 'scripts/collect-linux-p1.sh'), str(output / 'environment')],
                                cwd=ROOT, capture_output=True, text=True, timeout=30)
        (output / 'collector.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        collector_exit = result.returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        (output / 'collector.log').write_text(str(exc), encoding='utf-8')
        collector_exit = None
    scenarios = []
    for sid, probe, expected, prerequisites in PRIMITIVES:
        entry = {'id': sid, 'name': probe, 'level': 'primitive', 'prerequisites': prerequisites,
                 'expected': expected, 'status': 'UNAVAILABLE', 'actual': '', 'log': None}
        if not target_matches(info):
            entry['actual'] = 'exact target OS, architecture, running kernel and kernel package not established; not run'
        elif collector_exit != 0:
            entry['actual'] = 'environment evidence collection unavailable; not run'
        else:
            env = {**os.environ, 'PROBE_ROOT': str(work)}
            try:
                proc = subprocess.run([sys.executable, str(PROBES), probe], env=env, cwd=ROOT,
                                      capture_output=True, timeout=60)
                log = sid + '.log'
                (output / log).write_bytes(b'--- stdout ---\n' + proc.stdout + b'\n--- stderr ---\n' + proc.stderr)
                entry.update(status={0: 'PASS', 77: 'UNAVAILABLE'}.get(proc.returncode, 'FAIL'),
                             actual=f'probe exit={proc.returncode}; see log', log=log)
            except (OSError, subprocess.TimeoutExpired) as exc:
                entry['actual'] = f'probe could not complete: {exc}'
        scenarios.append(entry)
    for sid, name, expected in PENDING:
        scenarios.append({'id': sid, 'name': name, 'level': 'adapter', 'prerequisites': 'trusted snapshot/updater/admission implementation and isolated adversarial VM fixtures',
                          'expected': expected, 'status': 'NOT_RUN',
                          'actual': 'required implementation and independent acceptance harness do not exist', 'log': None})
    report = {'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'target_profile_gate': 'MATCH' if target_matches(info) else 'UNAVAILABLE',
              'profile_gate_scope': 'OS/architecture/kernel/package only; not P1 approval',
              'profile': info, 'collector_exit': collector_exit, 'scenarios': scenarios,
              'trusted_snapshot_approved': False, 'planner_admitted': False}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    for row in scenarios:
        print(f"{row['id']} {row['status']} {row['name']}: {row['actual']}")
    # A green process result must not conceal unimplemented acceptance scenarios.
    return 1 if any(row['status'] == 'FAIL' for row in scenarios) else 2 if any(row['status'] != 'PASS' for row in scenarios) else 0


if __name__ == '__main__':
    sys.exit(main())
