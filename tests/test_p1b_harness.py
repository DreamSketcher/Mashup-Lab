"""Harness checks only; no claims about Linux snapshot security."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/p1b/run.py'
spec = importlib.util.spec_from_file_location('p1b_harness', SCRIPT)
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


class HarnessTests(unittest.TestCase):
    def test_target_gate_exact(self):
        info = {'system': 'Linux', 'machine': 'x86_64', 'kernel': '6.8.0-31-generic',
                'os_release': 'ID=ubuntu\nVERSION_ID="24.04"\n', 'package_exit': 0,
                'package_stdout': '6.8.0-31.31 install ok installed'}
        self.assertTrue(harness.target_matches(info))
        for field, value in [('system', 'Darwin'), ('machine', 'aarch64'),
                             ('kernel', '6.8.0-32-generic'), ('package_exit', 1),
                             ('package_stdout', '6.8.0-32.32 install ok installed'),
                             ('os_release', 'ID=debian\nVERSION_ID="24.04"\n')]:
            altered = dict(info, **{field: value})
            with self.subTest(field=field): self.assertFalse(harness.target_matches(altered))
        self.assertFalse(harness.target_matches({'error': 'unavailable'}))

    def test_catalog_ids_unique_and_gaps_not_hidden(self):
        self.assertEqual(len(harness.PRIMITIVES), 5)
        self.assertEqual(len(harness.PENDING), 13)
        ids = [row[0] for row in harness.PRIMITIVES + harness.PENDING]
        self.assertEqual(len(ids), len(set(ids)))

    def test_refuse_without_ack_or_with_nonempty_workdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); work = root / 'work'; work.mkdir(); out = root / 'out'
            command = [sys.executable, str(SCRIPT), '--workdir', str(work), '--output', str(out)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(out.exists())
            (work / 'keep').write_text('do not remove')
            result = subprocess.run(command + ['--ack-disposable'], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((work / 'keep').read_text(), 'do not remove')
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
