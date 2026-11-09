#!/usr/bin/env python3
"""Small behavioral probes, not a security adapter; exit 0/1/77."""
import ctypes
import errno
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

class Unavailable(Exception): pass


def openat2_probe(root):
    if os.uname().machine != 'x86_64': raise Unavailable('only x86_64 syscall number specified')
    libc = ctypes.CDLL(None, use_errno=True)
    class How(ctypes.Structure):
        _fields_ = [('flags', ctypes.c_uint64), ('mode', ctypes.c_uint64), ('resolve', ctypes.c_uint64)]
    resolve = 0x08 | 0x04 | 0x02  # BENEATH, NO_SYMLINKS, NO_MAGICLINKS
    how = How(os.O_RDONLY | os.O_CLOEXEC, 0, resolve)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    def lookup(path):
        result = libc.syscall(437, fd, os.fsencode(path), ctypes.byref(how), ctypes.sizeof(how))
        if result < 0:
            e = ctypes.get_errno()
            if e in (errno.ENOSYS, errno.EPERM, errno.EACCES): raise Unavailable(f'openat2 blocked or unsupported errno={e}')
            raise OSError(e, os.strerror(e))
        return result
    return fd, lookup


def openat2():
    with tempfile.TemporaryDirectory(dir=BASE) as root:
        Path(root, 'ok').write_text('inside')
        os.symlink('ok', Path(root, 'link'))
        fd, lookup = openat2_probe(root)
        try:
            obj = lookup('ok'); assert os.read(obj, 10) == b'inside'; os.close(obj)
            for name, expected in [('link', errno.ELOOP), ('../outside', errno.EXDEV)]:
                try:
                    obj = lookup(name); os.close(obj)
                    raise AssertionError(f'{name} unexpectedly opened')
                except OSError as e:
                    if e.errno != expected: raise
            print('regular file accepted; symlink=ELOOP, escape=EXDEV')
        finally: os.close(fd)


def race():
    with tempfile.TemporaryDirectory(dir=BASE) as root:
        base = Path(root); (base / 'safe').mkdir(); (base / 'safe' / 'value').write_text('inside')
        (base / 'outside').mkdir(); (base / 'outside' / 'value').write_text('outside')
        os.symlink('outside', base / 'evil'); os.rename(base / 'safe', base / 'slot')
        fd, lookup = openat2_probe(root)
        stop = threading.Event(); errors = []
        def swap():
            try:
                while not stop.is_set():
                    os.rename(base / 'slot', base / 'safe')
                    os.rename(base / 'evil', base / 'slot')
                    os.rename(base / 'slot', base / 'evil')
                    os.rename(base / 'safe', base / 'slot')
            except Exception as e: errors.append(repr(e))
        worker = threading.Thread(target=swap); worker.start()
        counts = {'inside': 0, 'blocked': 0}
        try:
            for _ in range(10000):
                try:
                    obj = lookup('slot/value')
                    try:
                        content = os.read(obj, 100)
                        if content != b'inside': raise AssertionError(f'opened unchecked content: {content!r}')
                        counts['inside'] += 1
                    finally: os.close(obj)
                except OSError as e:
                    if e.errno not in (errno.ENOENT, errno.ELOOP, errno.EXDEV, errno.EAGAIN): raise
                    counts['blocked'] += 1
        finally:
            stop.set(); worker.join(); os.close(fd)
        if errors: raise AssertionError(errors)
        print('10000 concurrent directory/symlink swaps:', counts)
        if not counts['inside'] or not counts['blocked']:
            raise Unavailable('race did not observe both success and blocked cases')


def sealed_memfd():
    if not hasattr(os, 'memfd_create'): raise Unavailable('memfd_create unavailable')
    fd = os.memfd_create('policy-test', os.MFD_ALLOW_SEALING | os.MFD_CLOEXEC)
    try:
        os.write(fd, b'policy')
        seals = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals)
        if fcntl.fcntl(fd, fcntl.F_GET_SEALS) & seals != seals: raise AssertionError('missing seal')
        for name, op in [('write', lambda: os.pwrite(fd, b'x', 0)), ('shrink', lambda: os.ftruncate(fd, 1)), ('grow', lambda: os.ftruncate(fd, 100))]:
            try: op()
            except OSError as e:
                if e.errno != errno.EPERM: raise
                print(name, 'rejected with EPERM')
            else: raise AssertionError(name + ' unexpectedly succeeded')
        import mmap
        try:
            mapping = mmap.mmap(fd, 6, access=mmap.ACCESS_WRITE)
        except OSError as e:
            if e.errno not in (errno.EPERM, errno.EACCES): raise
            print('shared writable mapping rejected:', e.errno)
        else:
            mapping.close(); raise AssertionError('writable mapping unexpectedly allowed')
        assert os.pread(fd, 6, 0) == b'policy'
    finally: os.close(fd)


def flock_probe():
    with tempfile.TemporaryDirectory(dir=BASE) as root:
        path = Path(root, 'lock'); path.touch()
        f = open(path, 'r+'); fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        blocked = "import fcntl,sys; f=open(sys.argv[1],'r+');\ntry: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\nexcept BlockingIOError: sys.exit(0)\nsys.exit(1)"
        assert subprocess.run([sys.executable, '-c', blocked, str(path)]).returncode == 0
        path.rename(Path(root, 'old')); path.touch()
        other = open(path, 'r+')
        try: fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally: other.close()
        print('replacement creates independently lockable inode: lock-path protection required')
        f.close()
        child_code = "import fcntl,os,sys,time; f=open(sys.argv[1],'r+'); fcntl.flock(f,fcntl.LOCK_EX); print('locked',flush=True); time.sleep(60)"
        child = subprocess.Popen([sys.executable, '-c', child_code, str(path)], stdout=subprocess.PIPE, text=True)
        try:
            import select
            if not select.select([child.stdout], [], [], 5)[0]: raise Unavailable('child lock readiness timeout')
            if child.stdout.readline().strip() != 'locked': raise AssertionError('child failed')
            assert subprocess.run([sys.executable, '-c', blocked, str(path)]).returncode == 0
            child.kill(); child.wait(timeout=5)
            new = open(path, 'r+')
            try: fcntl.flock(new, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally: new.close()
            print('competitor blocked; lock released after killed child closed its only descriptor')
        finally:
            if child.poll() is None: child.kill(); child.wait(timeout=5)
            child.stdout.close()


def acl_probe(kind):
    import shutil
    if not all(shutil.which(x) for x in ('setfacl', 'getfacl', 'sudo')):
        raise Unavailable('ACL utilities or sudo missing')
    # Use a pre-existing numeric UID/GID, without changing system accounts.
    identity = ['sudo', '-n', '-u', '#65534', '-g', '#65534']
    if subprocess.run(identity + ['true']).returncode:
        raise Unavailable('sudo cannot run as uid/gid 65534')
    with tempfile.TemporaryDirectory(dir=BASE) as root:
        os.chmod(root, 0o755)
        if subprocess.run(identity + ['test', '-x', root]).returncode:
            raise Unavailable('uid 65534 cannot traverse temporary directory')
        file = Path(root, 'acl-test')
        def access(expected_write):
            code = ("import os,sys; p=sys.argv[1]; print('read:',open(p).read()); "
                    "expect=int(sys.argv[2]); "
                    "\ntry:\n fd=os.open(p,os.O_WRONLY); os.close(fd); result=1"
                    "\nexcept PermissionError: result=0"
                    "\nprint('write allowed:', result); sys.exit(0 if result==expect else 1)")
            result = subprocess.run(identity + [sys.executable, '-c', code, str(file), str(int(expected_write))],
                                    capture_output=True, text=True)
            print('access result:', result.returncode, result.stdout, result.stderr, flush=True)
            if result.returncode: raise AssertionError('access result differs from expected')
        def set_acl(*args):
            result = subprocess.run(['setfacl', *args], capture_output=True, text=True)
            print('setfacl:', result.returncode, result.stdout, result.stderr, flush=True)
            if result.returncode: raise Unavailable('cannot set POSIX ACL')
        if kind == 'user':
            file.write_text('acl-probe'); os.chmod(file, 0o600)
            set_acl('-m', 'u:65534:r--', str(file)); access(False)
            set_acl('-m', 'u:65534:rw-', str(file)); access(True)
        elif kind == 'group':
            file.write_text('acl-probe'); os.chmod(file, 0o600)
            set_acl('-m', 'g:65534:rw-', str(file)); access(True)
            set_acl('-m', 'm::r--', str(file)); access(False)
        elif kind == 'default':
            set_acl('-d', '-m', 'u:65534:rw-', root)
            fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o660)
            os.write(fd, b'acl-probe'); os.close(fd)
            access(True)
            print('new file inherited default ACL', flush=True)
        else:
            raise ValueError('unknown ACL probe')
        subprocess.run(['getfacl', '-p', root, str(file)], check=True)
        print(f'ACL {kind} access checks succeeded', flush=True)


def acl():
    # Backward-compatible P1-B primitive; all three cases must pass.
    for kind in ('user', 'group', 'default'):
        acl_probe(kind)


BASE = Path(os.environ['PROBE_ROOT'])
if __name__ == '__main__':
    try:
        {'openat2': openat2, 'path_race': race, 'memfd': sealed_memfd, 'flock': flock_probe, 'acl': acl, 'acl_user': lambda: acl_probe('user'),
         'acl_group': lambda: acl_probe('group'),
         'acl_default': lambda: acl_probe('default')}[sys.argv[1]]()
    except (Unavailable, NotImplementedError) as exc:
        print('UNAVAILABLE:', exc); sys.exit(77)
    except Exception as exc:
        print('FAIL:', repr(exc)); sys.exit(1)
    print('PASS: observed behavior only; not trusted-snapshot admission')
