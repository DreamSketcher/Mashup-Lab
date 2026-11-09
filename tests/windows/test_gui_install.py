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
            for name in ('Mashup-Lab.bat', 'Start-Mashup-Lab.bat', 'requirements.txt', 'requirements-gui.txt'):
                shutil.copy2(REPO / name, root / name)
            for name in ('mashup', 'scripts/windows'):
                shutil.copytree(REPO / name, root / name, ignore=shutil.ignore_patterns('__pycache__'))
            subprocess.run([sys.executable, '-m', 'venv', str(root / '.venv')], check=True, timeout=120)
            env = os.environ.copy()
            profile = root / 'profile'
            profile.mkdir()
            env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', QT_QPA_PLATFORM='offscreen', USERPROFILE=str(profile))
            result = subprocess.run([str(root / 'Mashup-Lab.bat')], cwd=tmp,
                                    input=b'1\n2\n1\n7\n', stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, env=env, timeout=600)
            output = result.stdout.decode('utf-8', 'replace')
            self.assertEqual(result.returncode, 0, output)
            self.assertIn('PySide6: не установлен', output)
            self.assertIn('FFmpeg: недоступен', output)
            self.assertIn('Окружение, интерфейс и FFmpeg готовы.', output)
            self.assertNotIn('Traceback (most recent call last)', output)
            self.assertIn('Интерфейс и FFmpeg установлены и проверены.', output)
            python = root / '.venv' / 'Scripts' / 'python.exe'
            check = subprocess.run([str(python), '-c',
                                    'import sys, PySide6; from PySide6.QtWidgets import QApplication; '
                                    'assert sys.version_info[:2] == (3,14); print(PySide6.__version__)'],
                                   text=True, capture_output=True, encoding='utf-8', timeout=30)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertEqual(check.stdout.strip(), '6.10.3')

            ffmpeg = subprocess.run([str(python), '-c',
                                     'import imageio_ffmpeg, subprocess; subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-version"], check=True)'],
                                    capture_output=True, timeout=30)
            self.assertEqual(ffmpeg.returncode, 0, ffmpeg.stderr.decode('utf-8', 'replace'))

            # A damaged executable in an otherwise installed wheel must be
            # reported by menu 1 and repaired by menu 8, not merely ignored by pip.
            exe = subprocess.run([str(python), '-c',
                                  'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'],
                                 text=True, capture_output=True, encoding='utf-8', check=True).stdout.strip()
            Path(exe).unlink()
            # Prevent a system FFmpeg on the hosted runner from masking damage.
            env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
            result = subprocess.run([str(root / 'Mashup-Lab.bat')], cwd=tmp,
                                    input=b'1\n8\n1\n7\n', stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, env=env, timeout=600)
            output = result.stdout.decode('utf-8', 'replace')
            self.assertEqual(result.returncode, 0, output)
            self.assertIn('FFmpeg: недоступен', output)
            self.assertIn('Попытка восстановить зависимости', output)
            self.assertIn('Интерфейс и FFmpeg установлены и проверены.', output)
            self.assertIn('Окружение, интерфейс и FFmpeg готовы.', output)

            # A newly declared dependency must be caught at runner startup.
            requirements = root / 'requirements-gui.txt'
            requirements.write_text(requirements.read_text(encoding='utf-8') + '\nmashup-future-test-package-does-not-exist>=1\n', encoding='utf-8')
            result = subprocess.run([str(root / 'Start-Mashup-Lab.bat')], cwd=tmp,
                                    input=b'\n', stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    env=env, timeout=120)
            output = result.stdout.decode('utf-8', 'replace')
            self.assertNotEqual(result.returncode, 0, output)
            self.assertIn('mashup-future-test-package-does-not-exist: не установлен', output)
            requirements.write_text(requirements.read_text(encoding='utf-8').replace('\nmashup-future-test-package-does-not-exist>=1\n', ''), encoding='utf-8')

            # The separate runner must start the actual GUI, not just import
            # its dependency. Only the temporary copied GUI gets a test timer
            # so the headless process closes without manual interaction.
            gui = root / 'mashup' / 'gui.py'
            code = gui.read_text(encoding='utf-8')
            before = 'window = MashupWindow(trace); window.show()'
            self.assertIn(before, code)
            code = code.replace(before, before + '\n        from PySide6.QtCore import QTimer\n        QTimer.singleShot(250, window.close)')
            gui.write_text(code, encoding='utf-8')
            result = subprocess.run([str(root / 'Start-Mashup-Lab.bat')], cwd=tmp,
                                    input=b'', stdout=subprocess.PIPE,
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
