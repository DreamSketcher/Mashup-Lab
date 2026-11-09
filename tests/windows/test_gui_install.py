"""Exercise menu 8 with an actual Python 3.14 environment on Windows."""
import json
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
            profile = root / 'profile'
            profile.mkdir()
            env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', QT_QPA_PLATFORM='offscreen', USERPROFILE=str(profile))
            result = subprocess.run([str(root / 'Mashup-Lab.bat')], cwd=tmp,
                                    input=b'2\n9\n8\n7\n', stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, env=env, timeout=600)
            output = result.stdout.decode('utf-8', 'replace')
            self.assertEqual(result.returncode, 0, output)
            self.assertIn('PySide6 не установлен. Выберите пункт 8', output)
            self.assertNotIn('Traceback (most recent call last)', output)
            self.assertIn('Интерфейс установлен.', output)
            python = root / '.venv' / 'Scripts' / 'python.exe'
            check = subprocess.run([str(python), '-c',
                                    'import sys, PySide6; from PySide6.QtWidgets import QApplication; '
                                    'assert sys.version_info[:2] == (3,14); print(PySide6.__version__)'],
                                   text=True, capture_output=True, encoding='utf-8', timeout=30)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertEqual(check.stdout.strip(), '6.10.3')

            # The real menu action must start the actual GUI, not just import
            # its dependency. Only the temporary copied GUI gets a test timer
            # so the headless process closes without manual interaction.
            gui = root / 'mashup' / 'gui.py'
            code = gui.read_text(encoding='utf-8')
            before = 'window = MashupWindow(trace); window.show()'
            self.assertIn(before, code)
            code = code.replace(before, before + '\n        from PySide6.QtCore import QTimer\n        QTimer.singleShot(250, window.close)')
            gui.write_text(code, encoding='utf-8')
            result = subprocess.run([str(root / 'Mashup-Lab.bat')], cwd=tmp,
                                    input=b'9\n7\n', stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, env=env, timeout=120)
            output = result.stdout.decode('utf-8', 'replace')
            self.assertEqual(result.returncode, 0, output)
            self.assertNotIn('NameError', output)
            self.assertNotIn('Ошибка интерфейса', output)
            files = list((profile / '.mashup-lab' / 'traces').glob('*.jsonl'))
            events = [[json.loads(line)['event'] for line in path.read_text(encoding='utf-8').splitlines()]
                      for path in files]
            self.assertTrue(any('ui.ready' in e and 'ui.closed' in e and 'application.exit' in e for e in events), events)


if __name__ == '__main__':
    unittest.main()
