"""Expose subprocess failure diagnostics on GitHub Actions."""
import subprocess
import sys
result = subprocess.run([sys.executable, *sys.argv[1:]], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
text = result.stdout.decode('utf-8', 'replace')
print(text, flush=True)
if result.returncode:
    text = text[-10000:]
    for i in range(0, len(text), 2000):
        print('::error title=Separation test::' + text[i:i+2000].replace('%','%25').replace('\r','%0D').replace('\n','%0A'), flush=True)
    sys.exit(result.returncode)
