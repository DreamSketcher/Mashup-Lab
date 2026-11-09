"""Run using an actual Python 3.10 on a Windows runner."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

assert sys.platform == 'win32' and sys.version_info[:2] == (3, 10)
repo = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp) / 'проверка старой версии'
    root.mkdir()
    shutil.copy2(repo / 'Mashup-Lab.bat', root)
    shutil.copytree(repo / 'scripts' / 'windows', root / 'scripts' / 'windows')
    shutil.copy2(repo / 'requirements.txt', root)
    env = os.environ.copy()
    env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + str(Path(env['SystemRoot']) / 'System32')
    result = subprocess.run([str(root / 'Mashup-Lab.bat')], cwd=tmp,
                            input=b'2\n7\n', stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=env, timeout=60)
    text = result.stdout.decode('utf-8', errors='replace')
    print(text)
    assert result.returncode != 0, text
    assert 'Python 3.11 или новее не найден' in text, text
    assert not (root / '.venv').exists()
print('Python 3.10 rejected before venv creation')
