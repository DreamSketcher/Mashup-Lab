"""Tests of the placeholder only, not of Linux security or isolation."""
import unittest
from pathlib import Path
from unittest.mock import patch

from mashup.linux_policy_snapshot import SnapshotStatus, capture_policy_snapshot


class SnapshotScaffoldTests(unittest.TestCase):
    def test_always_unavailable_and_no_policy_bytes(self):
        for path in [Path('/etc/mashup/policy.json'), Path('/not-found'), Path('.')]:
            with self.subTest(path=path):
                result = capture_policy_snapshot(path)
                self.assertIs(result.status, SnapshotStatus.UNAVAILABLE)
                self.assertIn('not implemented', result.reason)
                self.assertFalse(hasattr(result, 'policy_bytes'))

    def test_does_not_open_or_read_supplied_path(self):
        with patch('builtins.open', side_effect=AssertionError('unexpected file access')):
            with patch('os.open', side_effect=AssertionError('unexpected os.open')):
                result = capture_policy_snapshot(Path('/etc/mashup/policy.json'))
        self.assertIs(result.status, SnapshotStatus.UNAVAILABLE)

    def test_no_admit_or_pass_status(self):
        self.assertEqual({status.value for status in SnapshotStatus}, {'UNAVAILABLE'})


if __name__ == '__main__':
    unittest.main()
