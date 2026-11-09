"""Exercise menu 8 with an actual Python 3.14 environment on Windows."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]


@unittest.skipUnless(sys.platform == 'win32' and sys.version_info[:2] == (3, 14), 'requires Windows Python 3.14')
class WindowsGuiInstallTests(unittest.TestCase):
    def test_existing_python314_venv_gets_correct_gui_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'Проект & gui тест'
            root.mkdir()
            for name in ('Mashup-Lab.bat', 'requirements.txt', 'requirements-gui.txt'):
                shutil.copy2(REPO / name, root / name)
            for name in ('mashup', 'scripts/windows'):
                shutil.copytree(REPO / name, root / name, ignore=shutil.ignore_patterns('__pycache__'))
            subprocess.run([sys.executable, '-m', 'venv', str(root / '.venv')], check=True, timeout=120)
            env = os.environ.copy()
            env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
            result = subprocess.run([str(root / 'Mashup-Lab.bat')], cwd=tmp,
                                    input=b'2\n9\n8\n7\n', stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, env=env, timeout=600)
            output = result.stdout.decode('utf-8', 'replace')
            self.assertEqual(result.returncode, 0, output)
            self.assertIn('PySide6 не установлен. Выберите пункт 8.', output)
            self.assertNotIn("No module named 'PySide6'", output)
            self.assertIn('Интерфейс установлен.', output)
            python = root / '.venv' / 'Scripts' / 'python.exe'
            check = subprocess.run([str(python), '-c',
                                    'import sys, PySide6; from PySide6.QtWidgets import QApplication; '
                                    'assert sys.version_info[:2] == (3,14); print(PySide6.__version__)'],
                                   text=True, capture_output=True, encoding='utf-8', timeout=30)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertEqual(check.stdout.strip(), '6.10.3')


if __name__ == '__main__':
    unittest.main()
