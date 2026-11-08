"""Schema and byte-identity vectors only; no authorization/isolation tests."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from mashup.build_manifest import ManifestError, load_manifest, parse_manifest


FIXTURE = Path(__file__).parent / 'fixtures/planner/manifest-valid.json'
DIGEST = '8475dde84635714b169244497c7bf74f74f1e57b102199b64bc52dfac58b23c5'
ID = 'mashup-lab-timing/0.1/sha256:' + DIGEST


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.raw = FIXTURE.read_bytes()
        self.doc = json.loads(self.raw)

    def check_invalid(self, obj):
        with self.assertRaises(ManifestError):
            parse_manifest(json.dumps(obj).encode('utf-8'))

    def test_fixed_identity_and_expected_id(self):
        identity = parse_manifest(self.raw, ID)
        self.assertEqual(identity.sha256, DIGEST)
        self.assertEqual(identity.planner_id, ID)
        self.assertEqual(load_manifest(FIXTURE), identity)
        for wrong in [ID.upper(), ID[:-1] + '0', ID.replace('/0.1/', '/0.2/')]:
            with self.subTest(wrong=wrong), self.assertRaises(ManifestError):
                parse_manifest(self.raw, wrong)

    def test_byte_identity_not_semantic_identity(self):
        for changed in [self.raw + b' ', json.dumps(dict(reversed(list(self.doc.items())))).encode()]:
            with self.subTest(size=len(changed)):
                self.assertNotEqual(parse_manifest(changed).planner_id, ID)
                with self.assertRaises(ManifestError): parse_manifest(changed, ID)

    def test_bad_json_and_duplicates(self):
        variants = [b'\xff', b'\xef\xbb\xbf' + self.raw, self.raw[:-10], self.raw + b'x',
                    self.raw.replace(b'"manifest_version": "0.1",', b'"manifest_version": "0.1", "manifest_version": "0.1",'),
                    self.raw.replace(b'"version": "3.11.9",', b'"version": "3.11.9", "version": "3.11.9",'),
                    self.raw.replace(b'"git_dirty": null', b'"git_dirty": NaN'),
                    self.raw.replace(b'"git_dirty": null', b'"git_dirty": Infinity')]
        for raw in variants:
            with self.subTest(raw=raw[:30]), self.assertRaises(ManifestError): parse_manifest(raw)

    def test_required_and_unknown_fields(self):
        for scope in [(), ('python',), ('execution_image',), ('dependencies', 0)]:
            original = self.doc
            for part in scope: original = original[part]
            for key in original:
                p = copy.deepcopy(self.doc); node = p
                for part in scope: node = node[part]
                del node[key]
                with self.subTest(scope=scope, missing=key): self.check_invalid(p)
            p = copy.deepcopy(self.doc); node = p
            for part in scope: node = node[part]
            node['unexpected'] = 1
            with self.subTest(scope=scope, extra=True): self.check_invalid(p)

    def test_types_values_and_semantics(self):
        vectors = [
            (('manifest_version',), '0.2'), (('implementation',), 'other'),
            (('planner_contract_version',), '0.2'), (('engine_version',), ''),
            (('build_id',), None), (('git_dirty',), 1), (('git_dirty',), 'false'),
            (('git_commit',), 'A' * 40), (('git_commit',), 'a' * 39),
            (('python', 'implementation'), None), (('python', 'version'), 3.11),
            (('execution_image', 'isolation_policy'), 'unknown'),
            (('execution_image', 'platform'), 'linux'),
            (('execution_image', 'platform'), '/amd64'),
            (('execution_image', 'entrypoint'), '/bin/python'),
            (('execution_image', 'entrypoint'), []),
            (('execution_image', 'entrypoint'), ['']),
            (('execution_image', 'entrypoint'), ['/bin/python', None]),
            (('dependencies',), None),
        ]
        for path, value in vectors:
            p = copy.deepcopy(self.doc); node = p
            for part in path[:-1]: node = node[part]
            node[path[-1]] = value
            with self.subTest(path=path, value=value): self.check_invalid(p)
        for value in [True, False, None]:
            p = copy.deepcopy(self.doc); p['git_dirty'] = value
            parse_manifest(json.dumps(p).encode())
        for value in ['a' * 40, 'a' * 64, None]:
            p = copy.deepcopy(self.doc); p['git_commit'] = value
            parse_manifest(json.dumps(p).encode())

    def test_paths_and_digests(self):
        for path in ['relative', '/x/../y', '/x/./y', '/x//y', '//x', '/', '/x/', '/x\\y', '/x\0y']:
            p = copy.deepcopy(self.doc); p['python']['executable_path'] = path
            with self.subTest(path=path): self.check_invalid(p)
        for digest in ['1' * 64, 'sha256:' + 'A' * 64, 'sha256:' + '1' * 63,
                       'sha256:' + 'g' * 64, None]:
            for section, key in [('python', 'executable_sha256'), ('execution_image', 'oci_manifest_digest')]:
                p = copy.deepcopy(self.doc); p[section][key] = digest
                with self.subTest(section=section, digest=digest): self.check_invalid(p)
        p = copy.deepcopy(self.doc); p['dependencies'][0]['artifact_sha256'] = 'bad'
        self.check_invalid(p)
        p = copy.deepcopy(self.doc); p['dependencies'][0]['artifact_path'] = '../x'
        self.check_invalid(p)

    def test_dependency_normalization_and_sort(self):
        for name in ['PyYAML', 'a_b', 'a.b', '-abc', 'abc-', 'a--b', '', None]:
            p = copy.deepcopy(self.doc); p['dependencies'][0]['name'] = name
            with self.subTest(name=name): self.check_invalid(p)
        p = copy.deepcopy(self.doc); p['dependencies'].append(copy.deepcopy(p['dependencies'][0]))
        self.check_invalid(p)
        p['dependencies'][1]['name'] = 'aaa'
        self.check_invalid(p)
        p['dependencies'].reverse()
        parse_manifest(json.dumps(p).encode())
        p['dependencies'] = []
        parse_manifest(json.dumps(p).encode())

    def test_resource_limits(self):
        import tempfile
        from mashup.safe_json import MAX_BYTES, MAX_DEPTH, MAX_STRING_LENGTH
        with self.assertRaises(ManifestError): parse_manifest(b' ' * (MAX_BYTES + 1))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'huge.json'
            path.write_bytes(b' ' * (MAX_BYTES + 1))
            with self.assertRaises(ManifestError): load_manifest(path)
        with self.assertRaises(ManifestError): parse_manifest(b'[' * (MAX_DEPTH + 1) + b']' * (MAX_DEPTH + 1))
        p = copy.deepcopy(self.doc); p['build_id'] = 'a' * (MAX_STRING_LENGTH + 1)
        self.check_invalid(p)
        p['build_id'] = 'a' * MAX_STRING_LENGTH
        parse_manifest(json.dumps(p).encode())
        p = copy.deepcopy(self.doc)
        dep = p['dependencies'][0]
        p['dependencies'] = [{**dep, 'name': f'package-{i:04d}'} for i in range(1025)]
        self.check_invalid(p)

    def test_empty_root_control_and_unicode_paths(self):
        for data in [b'', b'null', b'[]', b'0', b'"object"', b'{"bad\nkey": 1}']:
            with self.subTest(data=data), self.assertRaises(ManifestError): parse_manifest(data)
        p = copy.deepcopy(self.doc); p['python']['executable_path'] = '/opt/音声/питон'
        parse_manifest(json.dumps(p, ensure_ascii=False).encode('utf-8'))
        p['python']['executable_path'] = '/opt/\x00python'
        self.check_invalid(p)
        p['python']['executable_path'] = '/opt/\ud800'
        self.check_invalid(p)

    def test_cli_identity_not_trust(self):
        command = [sys.executable, '-m', 'mashup', 'inspect-manifest', str(FIXTURE)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'planner_id': ID, 'sha256': DIGEST,
                                                      'trust': 'not_checked', 'execution': 'not_checked'})
        result = subprocess.run(command[:-1] + ['missing.json'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertIn('error:', result.stderr)


if __name__ == '__main__':
    unittest.main()
