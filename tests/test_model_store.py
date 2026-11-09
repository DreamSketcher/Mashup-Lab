import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mashup import model_store


class ModelStoreTests(unittest.TestCase):
    def test_validate_hash_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'asset'
            path.write_bytes(b'hello')
            sha = hashlib.sha256(b'hello').hexdigest()
            self.assertTrue(model_store.valid(path, sha, 5))
            self.assertFalse(model_store.valid(path, sha, 6))
            path.write_bytes(b'wrong')
            self.assertFalse(model_store.valid(path, sha, 5))
            with patch.dict(model_store.ASSETS, {'test': ('https://example.com', sha, 5)}, clear=True):
                self.assertFalse(model_store.check(tmp))
