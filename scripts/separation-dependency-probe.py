"""Expose compatibility probe diagnostics as workflow annotations."""
import subprocess
import sys

version = sys.argv[1]
cmd = [sys.executable, '-m', 'pip', 'install', f'audio-separator=={version}',
       'onnxruntime', 'imageio-ffmpeg', 'librosa==0.11.0']
if sys.version_info >= (3, 13):
    cmd.append('audioop-lts')
result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
text = result.stdout.decode('utf-8', 'replace')
print(text, flush=True)
if result.returncode:
    text = text[-9000:]
    for i in range(0, len(text), 2000):
        escaped = text[i:i+2000].replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        print('::error title=Engine installation::' + escaped, flush=True)
    sys.exit(result.returncode)
