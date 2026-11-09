"""Run Windows tests and expose failures as Actions annotations for diagnosis."""
import subprocess
import sys

result = subprocess.run([sys.executable, 'tests/windows/test_launcher.py', '-v'],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
text = result.stdout.decode('utf-8', errors='replace')
print(text, flush=True)
if result.returncode:
    escaped = text[-30000:].replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    print('::error title=Windows launcher test failure::' + escaped, flush=True)
sys.exit(result.returncode)
