"""Parse build-manifest bytes and compute their identity, without trusting them.

No files inside the claimed image are opened, and no authorization is performed.
"""
import hashlib
import posixpath
import re
from dataclasses import dataclass
from .safe_json import decode, read_bounded, SafeJSONError


class ManifestError(ValueError):
    """Invalid manifest bytes, schema, or expected identity."""


def _fields(value, keys, name):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ManifestError(f'{name}: expected fields {", ".join(keys)}')


def _string(value, name):
    if not isinstance(value, str) or not value or '\x00' in value or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ManifestError(f'{name}: expected nonempty Unicode string without NUL')
    return value


def _digest(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', value):
        raise ManifestError(f'{name}: invalid SHA-256 digest')


def _path(value, name):
    _string(value, name)
    if not value.startswith('/') or value.startswith('//') or value == '/' or posixpath.normpath(value) != value or '\\' in value:
        raise ManifestError(f'{name}: expected normalized absolute POSIX file path')


def _literal(value, expected, name):
    if value != expected or not isinstance(value, str):
        raise ManifestError(f'{name}: unsupported value')


def _validate(manifest):
    _fields(manifest, ('manifest_version', 'implementation', 'planner_contract_version',
                       'engine_version', 'build_id', 'git_commit', 'git_dirty',
                       'python', 'dependencies', 'execution_image'), 'manifest')
    _literal(manifest['manifest_version'], '0.1', 'manifest_version')
    _literal(manifest['implementation'], 'mashup-lab-timing', 'implementation')
    _literal(manifest['planner_contract_version'], '0.1', 'planner_contract_version')
    _string(manifest['engine_version'], 'engine_version')
    _string(manifest['build_id'], 'build_id')
    commit = manifest['git_commit']
    if commit is not None and (not isinstance(commit, str) or not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', commit)):
        raise ManifestError('git_commit: invalid object ID')
    dirty = manifest['git_dirty']
    if dirty is not None and type(dirty) is not bool:
        raise ManifestError('git_dirty: expected boolean or null')
    python = manifest['python']
    _fields(python, ('implementation', 'version', 'executable_path', 'executable_sha256'), 'python')
    _string(python['implementation'], 'python.implementation')
    _string(python['version'], 'python.version')
    _path(python['executable_path'], 'python.executable_path')
    _digest(python['executable_sha256'], 'python.executable_sha256')
    dependencies = manifest['dependencies']
    if not isinstance(dependencies, list):
        raise ManifestError('dependencies: expected array')
    if len(dependencies) > 1024:
        raise ManifestError('dependencies: exceeds count limit')
    names = []
    for dep in dependencies:
        _fields(dep, ('name', 'version', 'artifact_path', 'artifact_sha256'), 'dependency')
        name = dep['name']
        if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name):
            raise ManifestError('dependency.name: expected normalized distribution name')
        names.append(name)
        _string(dep['version'], 'dependency.version')
        _path(dep['artifact_path'], 'dependency.artifact_path')
        _digest(dep['artifact_sha256'], 'dependency.artifact_sha256')
    if names != sorted(set(names)):
        raise ManifestError('dependencies: names must be unique and sorted')
    image = manifest['execution_image']
    _fields(image, ('platform', 'oci_manifest_digest', 'entrypoint', 'isolation_policy'), 'execution_image')
    platform = image['platform']
    if not isinstance(platform, str) or not re.fullmatch(r'[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)?', platform):
        raise ManifestError('execution_image.platform: invalid platform')
    _digest(image['oci_manifest_digest'], 'execution_image.oci_manifest_digest')
    entrypoint = image['entrypoint']
    if not isinstance(entrypoint, list) or not entrypoint:
        raise ManifestError('execution_image.entrypoint: expected nonempty array')
    for arg in entrypoint:
        if not isinstance(arg, str) or '\x00' in arg or any(0xD800 <= ord(c) <= 0xDFFF for c in arg):
            raise ManifestError('execution_image.entrypoint: invalid argument')
    if not entrypoint[0]:
        raise ManifestError('execution_image.entrypoint: executable is empty')
    _literal(image['isolation_policy'], 'offline-readonly-v1', 'execution_image.isolation_policy')


@dataclass(frozen=True)
class ManifestIdentity:
    """Identity of a structurally valid manifest, not an authorization."""
    planner_id: str
    sha256: str
    image_digest: str
    platform: str


def parse_manifest(data: bytes, expected_planner_id: str | None = None) -> ManifestIdentity:
    """Validate exact UTF-8 JSON bytes and return their untrusted identity."""
    if not isinstance(data, bytes):
        raise TypeError('manifest must be bytes')
    try:
        manifest = decode(data)
        _validate(manifest)
    except ManifestError:
        raise
    except SafeJSONError as exc:
        raise ManifestError(f'invalid manifest JSON: {exc}') from exc
    digest = hashlib.sha256(data).hexdigest()
    planner_id = f'mashup-lab-timing/0.1/sha256:{digest}'
    if expected_planner_id is not None and expected_planner_id != planner_id:
        raise ManifestError('planner_id does not match manifest bytes and contract')
    return ManifestIdentity(planner_id=planner_id, sha256=digest,
                            image_digest=manifest['execution_image']['oci_manifest_digest'],
                            platform=manifest['execution_image']['platform'])


def load_manifest(path, expected_planner_id: str | None = None) -> ManifestIdentity:
    try:
        data = read_bounded(path)
    except (OSError, SafeJSONError) as exc:
        raise ManifestError(f'cannot read manifest: {exc}') from exc
    return parse_manifest(data, expected_planner_id)
