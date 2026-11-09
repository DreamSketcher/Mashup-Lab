"""End-to-end launcher checks; run only on real Windows, not Wine."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave

import yaml

REPO = Path(__file__).resolve().parents[2]


@unittest.skipUnless(sys.platform == 'win32', 'requires Windows')
class WindowsLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / 'Проект & тест ! %MASHUP_LAUNCHER_UNSET% и (пробел)'
        cls.root.mkdir()
        for name in ('Mashup-Lab.bat', 'pyproject.toml', 'requirements.txt', 'requirements-gui.txt'):
            shutil.copy2(REPO / name, cls.root / name)
        for name in ('mashup', 'scripts/windows', 'docs'):
            shutil.copytree(REPO / name, cls.root / name, ignore=shutil.ignore_patterns('__pycache__'))
        src = cls.root / 'звук & ! %.wav'
        with wave.open(str(src), 'wb') as w:
            w.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
            w.writeframes(b'\x00\x40' * 50)
        project = {'schema_version': '0.1',
            'timeline': {'bpm': 120, 'time_signature': [4, 4], 'ppq': 960, 'sample_rate': 48000},
            'sources': [{'id': 's', 'path': src.name, 'sha256': hashlib.sha256(src.read_bytes()).hexdigest(), 'sample_rate': 48000, 'channels': 1, 'frames': 50}],
            'clips': [{'id': 'a', 'source_id': 's', 'source_range': {'start_frame': 0, 'end_frame': 50}, 'position': {'bar': 1, 'beat': 1, 'tick': 0}, 'processing': {'duration_ratio': 1, 'pitch_semitones': 0, 'gain_db': 0, 'pan': 0, 'fade_in_frames': 0, 'fade_out_frames': 0}}],
            'render': {'bit_depth': 16}}
        cls.project = cls.root / 'музыка & ! %.yaml'
        cls.project.write_text(yaml.safe_dump(project, allow_unicode=True), encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_launcher(self, *lines, env=None):
        result = subprocess.run([str(self.root / 'Mashup-Lab.bat')], cwd=tempfile.gettempdir(),
            input=('\n'.join(lines) + '\n').encode('utf-8'), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, env=env, timeout=300)
        output = result.stdout.decode('utf-8', errors='replace')
        return result.returncode, output

    def test_00_python_missing_and_incompatible(self):
        env = os.environ.copy()
        env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
        code, out = self.run_launcher('2', '7', env=env)
        self.assertNotEqual(code, 0, out)
        self.assertIn('Python 3.11 или новее не найден', out)
        self.assertFalse((self.root / '.venv').exists())
        # cmd.exe pretending to be python.exe cannot pass the version probe.
        fake = self.root / 'fake-python'
        fake.mkdir()
        shutil.copy2(Path(os.environ['SystemRoot']) / 'System32' / 'cmd.exe', fake / 'python.exe')
        env['PATH'] = str(fake) + os.pathsep + env['PATH']
        code, out = self.run_launcher('2', '7', env=env)
        self.assertNotEqual(code, 0, out)
        self.assertIn('Python 3.11 или новее не найден', out)
        self.assertFalse((self.root / '.venv').exists())

    def test_full_lifecycle(self):
        # Start without an environment; a failed offline install must remain a failure.
        env = os.environ.copy()
        env.update(PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1')
        code, out = self.run_launcher('2', '7', env=env)
        self.assertNotEqual(code, 0, out)
        self.assertIn('Ошибка установки', out)
        self.assertFalse((self.root / '.venv' / 'mashup-requirements.sha256').exists())
        code, out = self.run_launcher('2', '7')
        self.assertEqual(code, 0, out)
        self.assertIn('Окружение готово.', out)
        code, out = self.run_launcher('2', '7')
        self.assertEqual(code, 0, out)
        self.assertIn('переустановка не требуется', out)
        code, out = self.run_launcher('3', str(self.project), '4', str(self.project), '7')
        self.assertEqual(code, 0, out)
        self.assertIn('"total_frames": 50', out)
        output = self.root / 'результат & ! %.wav'
        code, out = self.run_launcher('5', str(self.project), str(output), '7')
        self.assertEqual(code, 0, out)
        self.assertTrue(output.is_file(), out)
        with wave.open(str(output), 'rb') as w:
            self.assertEqual((w.getnchannels(), w.getframerate(), w.getnframes()), (2, 48000, 50))
        before = output.read_bytes()
        code, out = self.run_launcher('5', str(self.project), str(output), '7')
        self.assertNotEqual(code, 0, out)
        self.assertEqual(before, output.read_bytes())
        self.project.write_text('invalid: yaml', encoding='utf-8')
        code, out = self.run_launcher('3', str(self.project), '7')
        self.assertEqual(code, 1, out)
        self.assertIn('error:', out)
        self.assertIn('Ошибка CLI', out)


if __name__ == '__main__':
    unittest.main()
