"""Exercise actual diagnostic menu 9 on the Windows CPU inference runner."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]


@unittest.skipUnless(sys.platform == 'win32' and sys.version_info[:2] == (3, 12), 'requires Windows Python 3.12')
class EngineInstallTest(unittest.TestCase):
    def test_menu_9_installs_model_and_validates_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'Проект & обработка'; root.mkdir()
            for name in ('Mashup-Lab.bat', 'requirements.txt', 'requirements-gui.txt', 'requirements-separation.txt'):
                shutil.copy2(REPO / name, root / name)
            for name in ('mashup', 'scripts/windows'):
                shutil.copytree(REPO / name, root / name, ignore=shutil.ignore_patterns('__pycache__'))
            subprocess.run([sys.executable, '-m', 'venv', '--system-site-packages', str(root / '.venv-separation')], check=True, timeout=120)
            profile = root / 'profile'; model_dir = profile / '.mashup-lab' / 'models' / 'uvr-mdx-hq3'; model_dir.mkdir(parents=True)
            shutil.copy2(Path(os.environ['RUNNER_TEMP']) / 'model.onnx', model_dir / 'UVR-MDX-NET-Inst_HQ_3.onnx')
            env = os.environ.copy(); env.update(USERPROFILE=str(profile), PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
            result = subprocess.run([str(root / 'Mashup-Lab.bat')], cwd=tmp, input=b'9\n7\n\n', stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, env=env, timeout=600)
            output = result.stdout.decode('utf-8', 'replace')
            self.assertEqual(result.returncode, 0, output)
            self.assertIn('Движок и модель установлены.', output)
            self.assertIn('Движок UVR и модель: OK', output)
            self.assertTrue((model_dir / 'download_checks.json').is_file())


if __name__ == '__main__':
    unittest.main()
