"""Exercise the real private NuGet runtime and venv on Windows."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]


@unittest.skipUnless(sys.platform == 'win32', 'requires Windows')
class LocalPythonTests(unittest.TestCase):
    def test_download_create_venv_and_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'Проект & Python (тест)'; root.mkdir()
            scripts = root / 'scripts' / 'windows'
            shutil.copytree(REPO / 'scripts/windows', scripts)
            bootstrap = scripts / 'separation-python.ps1'
            shutil.copy2(REPO / 'Mashup-Lab.bat', root / 'Mashup-Lab.bat')
            shutil.copy2(REPO / 'requirements-separation.txt', root / 'requirements-separation.txt')
            shutil.copytree(REPO / 'mashup', root / 'mashup', ignore=shutil.ignore_patterns('__pycache__'))
            gui = root / '.venv'; gui.mkdir()
            sentinel = gui / 'do-not-touch'; sentinel.write_text('keep', encoding='utf-8')
            env = os.environ.copy()
            env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
            env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
            def run():
                return subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                       '-File', str(bootstrap), '-ProjectRoot', str(root)],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=240)
            # Exercise menu 9 without any Python on PATH. Stop deliberately at pip,
            # before large engine downloads; the test does not claim full installation.
            env['PIP_NO_INDEX'] = '1'
            result = subprocess.run([str(root / 'Mashup-Lab.bat')], cwd=tmp, input=b'9\n7\n\n',
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=360)
            output = result.stdout.decode('utf-8', 'replace')
            self.assertNotEqual(result.returncode, 0, output)
            self.assertIn('Установка движка не удалась', output)
            self.assertEqual(sentinel.read_text(encoding='utf-8'), 'keep')
            python = root / '.python-separation' / 'python.exe'
            self.assertTrue(python.is_file(), output)
            venv = root / '.venv-separation'
            python_venv = venv / 'Scripts' / 'python.exe'
            subprocess.run([str(python_venv), str(scripts / 'check-python312.py')], env=env, check=True, timeout=30)
            subprocess.run([str(python_venv), '-m', 'pip', '--version'], env=env, check=True, timeout=30)
            before = python.stat().st_mtime_ns
            result = run()
            self.assertEqual(result.returncode, 0, result.stdout.decode('utf-8', 'replace'))
            self.assertEqual(before, python.stat().st_mtime_ns)
            self.assertFalse(list(root.glob('.python-separation-download-*')))

    def test_existing_bad_runtime_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / '.python-separation'; target.mkdir()
            sentinel = target / 'do-not-delete.txt'; sentinel.write_text('keep', encoding='utf-8')
            result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                     '-File', str(REPO / 'scripts/windows/separation-python.ps1'),
                                     '-ProjectRoot', str(root)], stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(sentinel.read_text(encoding='utf-8'), 'keep')


if __name__ == '__main__':
    unittest.main()
