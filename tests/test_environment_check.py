import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from importlib import metadata

from mashup import environment_check as check


class EnvironmentTests(unittest.TestCase):
    def test_recursive_requirements_markers_and_new_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'base.txt').write_text('known>=2\nmissing-future>=1\nignored; python_version < "1"\n')
            (root / 'gui.txt').write_text('-r base.txt\nknown<4\n')
            def version(name):
                if name == 'known': return '3.0'
                raise metadata.PackageNotFoundError(name)
            out = io.StringIO()
            with patch.object(check.metadata, 'version', side_effect=version), contextlib.redirect_stdout(out):
                self.assertFalse(check.check_requirements(root / 'gui.txt'))
            self.assertIn('missing-future: не установлен', out.getvalue())
            self.assertNotIn('ignored:', out.getvalue())
            (root / 'base.txt').write_text('known>=4\n')
            with patch.object(check.metadata, 'version', return_value='3.0'), contextlib.redirect_stdout(out):
                self.assertFalse(check.check_requirements(root / 'gui.txt'))
            self.assertIn('не соответствует', out.getvalue())

    def test_unsupported_or_recursive_requirements_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'req.txt'
            path.write_text('-r req.txt\n')
            with self.assertRaises(ValueError): list(check.declared_requirements(path))
            path.write_text('--index-url https://example.invalid\n')
            with self.assertRaises(ValueError): list(check.declared_requirements(path))

    def test_new_runtime_probe_failure_blocks_start(self):
        with patch.object(check, 'check_requirements', return_value=True), \
             patch.object(check.subprocess, 'run') as run, \
             patch.object(check, 'PROBES', [('future', lambda: 1/0)]), \
             contextlib.redirect_stdout(io.StringIO()):
            run.return_value.returncode = 0
            self.assertEqual(check.main(), 1)
