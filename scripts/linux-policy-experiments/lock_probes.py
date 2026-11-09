#!/usr/bin/env python3
"""Experimental cooperative flock demonstrations, not trusted admission."""
import errno
import fcntl
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time

BASE = Path(os.environ['PROBE_ROOT'])


class Unavailable(Exception):
    pass


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def read_line(proc, timeout=5):
    deadline = time.monotonic() + timeout
    data = bytearray()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([proc.stdout], [], [], remaining)[0]:
            raise Unavailable('process handshake timed out')
        byte = os.read(proc.stdout.fileno(), 1)
        if not byte:
            raise AssertionError(f'child exited early: {proc.poll()}')
        if byte == b'\n':
            return data.decode('utf-8')
        data.extend(byte)


def stop(proc):
    if proc.poll() is None:
        proc.kill()
    proc.wait(timeout=5)
    if proc.stdout:
        proc.stdout.close()


def swap_hazards():
    with tempfile.TemporaryDirectory(dir=BASE) as name:
        root = Path(name)
        parent = root / 'chain'; parent.mkdir()
        path = parent / 'lock'; path.touch()
        with path.open('r+') as old:
            fcntl.flock(old, fcntl.LOCK_EX | fcntl.LOCK_NB)
            path.rename(parent / 'old-lock'); path.touch()
            with path.open('r+') as new:
                fcntl.flock(new, fcntl.LOCK_EX | fcntl.LOCK_NB)
                check(os.fstat(old.fileno()).st_ino != os.fstat(new.fileno()).st_ino, 'file inode did not change')
            # Hold old lock while substituting the directory path too.
            parent.rename(root / 'moved'); parent.mkdir(); (parent / 'lock').touch()
            with (parent / 'lock').open('r+') as replacement:
                fcntl.flock(replacement, fcntl.LOCK_EX | fcntl.LOCK_NB)
                check(os.fstat(old.fileno()).st_ino != os.fstat(replacement.fileno()).st_ino, 'parent replacement did not change lock inode')
        print('file and parent replacement each produced an independently lockable inode')


def unprivileged_replacement_denied():
    import shutil
    if not shutil.which('sudo'):
        raise Unavailable('sudo unavailable')
    user = ['sudo', '-n', '-u', '#65534', '-g', '#65534']
    if subprocess.run(user + ['true']).returncode:
        raise Unavailable('uid/gid 65534 unavailable')
    with tempfile.TemporaryDirectory(dir=BASE) as name:
        root = Path(name); os.chmod(root, 0o755)
        parent = root / 'chain'; parent.mkdir(mode=0o755)
        lock = parent / 'lock'; lock.touch(mode=0o644)
        for directory in (root, parent):
            if subprocess.run(user + ['test', '-x', str(directory)]).returncode:
                raise Unavailable('unprivileged user cannot traverse test path')
        script = '''import os,sys
for src,dst in ((sys.argv[1],sys.argv[1]+'.renamed'),(sys.argv[2],sys.argv[2]+'.renamed')):
    try: os.rename(src,dst)
    except PermissionError: print('denied:',src)
    else: raise SystemExit('rename unexpectedly succeeded: '+src)
'''
        proc = subprocess.run(user + [sys.executable, '-c', script, str(lock), str(parent)],
                              capture_output=True, text=True)
        print('negative-user:', proc.returncode, proc.stdout, proc.stderr)
        if proc.returncode:
            raise AssertionError('negative-user rename checks failed or could not run')
        check(lock.exists() and parent.exists(), 'protected test objects disappeared')
    print('mode-based test denied unprivileged file and parent renames; ACLs and capabilities not proven')


WRITER = '''import fcntl,os,sys
root=sys.argv[1]
f=open(root+'/lock','r+')
print('waiting',flush=True)
fcntl.flock(f,fcntl.LOCK_EX)
print('acquired',flush=True)
with open(root+'/new','w') as x: x.write('revoked'); x.flush(); os.fsync(x.fileno())
os.replace(root+'/new',root+'/policy')
print('published',flush=True)
'''


def coordination():
    with tempfile.TemporaryDirectory(dir=BASE) as name:
        root = Path(name); (root / 'lock').touch(); (root / 'policy').write_text('active')
        with (root / 'lock').open('r+') as reader:
            fcntl.flock(reader, fcntl.LOCK_SH)
            snapshot = (root / 'policy').read_text()
            proc = subprocess.Popen([sys.executable, '-u', '-c', WRITER, name], stdout=subprocess.PIPE)
            try:
                check(read_line(proc) == 'waiting', 'writer not ready')
                ready, _, _ = select.select([proc.stdout], [], [], 0.5)
                check(not ready, 'writer acquired while reader holds shared lock')
                check((root / 'policy').read_text() == 'active', 'policy changed under shared lock')
                # Simulated decision is made while the reader holds the lock.
                decision = snapshot
                check(decision == 'active', 'unexpected decision snapshot')
                fcntl.flock(reader, fcntl.LOCK_UN)
                check(read_line(proc) == 'acquired', 'writer failed to acquire')
                check(read_line(proc) == 'published', 'writer failed to publish')
                check(proc.wait(timeout=5) == 0, 'writer failed')
            finally:
                stop(proc)
        with (root / 'lock').open('r+') as later:
            fcntl.flock(later, fcntl.LOCK_SH)
            check((root / 'policy').read_text() == 'revoked', 'subsequent reader missed update')
        print('reader decision under shared lock precedes writer; later reader sees update')
        print('simulated ordering only: no production admission or durable decision record')


CRASH = '''import fcntl,os,sys
root,phase=sys.argv[1:]
f=open(root+'/lock','r+'); fcntl.flock(f,fcntl.LOCK_EX)
with open(root+'/new','w') as out: out.write('new-complete'); out.flush(); os.fsync(out.fileno())
if phase=='after': os.replace(root+'/new',root+'/policy')
os._exit(31)
'''


def crash_publication():
    with tempfile.TemporaryDirectory(dir=BASE) as name:
        root = Path(name); (root / 'lock').touch(); policy = root / 'policy'
        for phase, expected in [('before', 'old-complete'), ('after', 'new-complete')]:
            policy.write_text('old-complete')
            result = subprocess.run([sys.executable, '-c', CRASH, name, phase], timeout=5)
            check(result.returncode == 31, f'unexpected updater exit: {result.returncode}')
            with (root / 'lock').open('r+') as reader:
                fcntl.flock(reader, fcntl.LOCK_SH | fcntl.LOCK_NB)
                check(policy.read_text() == expected, f'{phase}: unexpected policy content')
            print(f'{phase} rename: complete {expected}; dead sole holder released lock')
        print('process-exit test only; no VM power loss or fsync-directory durability guarantee')


if __name__ == '__main__':
    try:
        {'lock_swap': swap_hazards, 'lock_permissions': unprivileged_replacement_denied,
         'lock_coordination': coordination, 'lock_crash': crash_publication}[sys.argv[1]]()
    except (Unavailable, NotImplementedError) as exc:
        print('UNAVAILABLE:', exc); sys.exit(77)
    except Exception as exc:
        print('FAIL:', repr(exc)); sys.exit(1)
    print('PASS: toy protocol observation only; no trusted admission')
