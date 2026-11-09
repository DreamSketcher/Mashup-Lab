"""Policy schema and claims comparison, not trusted policy or runtime checks."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mashup.build_manifest import load_manifest
from mashup.trust_policy import PolicyError, compare_policy, load_policy, parse_policy

FIXTURE = Path(__file__).parent / 'fixtures/planner/manifest-valid.json'
ID = 'mashup-lab-timing/0.1/sha256:8475dde84635714b169244497c7bf74f74f1e57b102199b64bc52dfac58b23c5'


def good():
    return {'policy_version': '0.1', 'entries': [{'planner_id': ID,
            'image_digest': 'sha256:' + '3' * 64, 'platform': 'linux/amd64', 'status': 'active'}]}


def encode(obj):
    return json.dumps(obj).encode()


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.manifest = load_manifest(FIXTURE)

    def test_match_not_authorization(self):
        self.assertEqual(compare_policy(self.manifest, parse_policy(encode(good()))), 'MATCH')
        self.assertEqual(compare_policy(self.manifest, parse_policy(b'{"policy_version":"0.1","entries":[]}')), 'NOT_LISTED')
        p = good(); p['entries'][0]['status'] = 'revoked'
        self.assertEqual(compare_policy(self.manifest, parse_policy(encode(p))), 'REVOKED')
        for key, value in [('platform', 'linux/arm64'), ('image_digest', 'sha256:' + '4' * 64)]:
            p = good(); p['entries'][0][key] = value
            with self.subTest(key=key):
                self.assertEqual(compare_policy(self.manifest, parse_policy(encode(p))), 'MISMATCH')

    def test_duplicate_id_entire_policy_invalid_even_if_revoked(self):
        p = good(); entry = copy.deepcopy(p['entries'][0]); entry['status'] = 'revoked'
        p['entries'].append(entry)
        with self.assertRaises(PolicyError): parse_policy(encode(p))

    def test_malformed_and_strict_shape(self):
        for raw in [b'', b'\xff', b'{}', b'null', b'{"policy_version":"0.1","policy_version":"0.1","entries":[]}',
                    b'{"policy_version":"0.1","entries":[],"x":NaN}']:
            with self.subTest(raw=raw), self.assertRaises(PolicyError): parse_policy(raw)
        variants = []
        p = good(); p['policy_version'] = '0.2'; variants.append(p)
        p = good(); p['entries'] = None; variants.append(p)
        p = good(); p['extra'] = 0; variants.append(p)
        for key, value in [('planner_id', ID.upper()), ('image_digest', 'x'), ('platform', 'linux'),
                           ('status', 'allow'), ('status', True)]:
            p = good(); p['entries'][0][key] = value; variants.append(p)
        p = good(); p['entries'][0]['extra'] = 1; variants.append(p)
        p = good(); del p['entries'][0]['status']; variants.append(p)
        p = good(); p['entries'] = [copy.deepcopy(p['entries'][0]) for _ in range(1025)]; variants.append(p)
        for p in variants:
            with self.subTest(value=str(p)[:120]), self.assertRaises(PolicyError): parse_policy(encode(p))

    def test_cli_comparison_and_missing_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'policy.json'
            command = [sys.executable, '-m', 'mashup', 'compare-policy', str(FIXTURE), str(path)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)['comparison'], 'UNAVAILABLE')
            path.write_bytes(encode(good()))
            self.assertEqual(len(load_policy(path).entries), 1)
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {'comparison': 'MATCH', 'trust': 'not_checked', 'execution': 'not_checked'})
            p = good(); p['entries'][0]['status'] = 'revoked'; path.write_bytes(encode(p))
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)['comparison'], 'REVOKED')
            path.write_bytes(b'bad')
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)['comparison'], 'UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()
