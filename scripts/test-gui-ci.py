"""Run GUI checks and expose failure output as Actions annotations."""
import subprocess
import sys

commands = [
    [sys.executable, '-c', 'from PySide6.QtWidgets import QApplication; from mashup.gui import MashupWindow'],
    [sys.executable, '-c', 'import imageio_ffmpeg; import subprocess; subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-version"], check=True, stdout=subprocess.PIPE)'],
    [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_conversion.py', '-v'],
    [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_gui.py', '-v'],
]
for command in commands:
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = result.stdout.decode('utf-8', errors='replace')
    print(text, flush=True)
    if result.returncode:
        for i in range(0, len(text), 2000):
            escaped = text[i:i + 2000].replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
            print('::error title=GUI test failure::' + escaped, flush=True)
        sys.exit(result.returncode)
