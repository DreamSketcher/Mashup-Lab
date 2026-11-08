"""Strict policy parsing and comparison only; not an authorization gate."""
from dataclasses import dataclass
import re

from .build_manifest import ManifestIdentity
from .safe_json import SafeJSONError, decode, read_bounded

MAX_ENTRIES = 1024
_ID = re.compile(r'mashup-lab-timing/0\.1/sha256:[0-9a-f]{64}')
_DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
_PLATFORM = re.compile(r'[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)?')


class PolicyError(ValueError):
    """The supplied policy could not be read or parsed."""


@dataclass(frozen=True)
class Entry:
    planner_id: str
    image_digest: str
    platform: str
    status: str


@dataclass(frozen=True)
class Policy:
    entries: tuple[Entry, ...]


def parse_policy(data: bytes) -> Policy:
    try:
        obj = decode(data)
    except SafeJSONError as exc:
        raise PolicyError(f'invalid policy JSON: {exc}') from exc
    if not isinstance(obj, dict) or set(obj) != {'policy_version', 'entries'}:
        raise PolicyError('policy: invalid fields')
    if obj['policy_version'] != '0.1' or not isinstance(obj['policy_version'], str):
        raise PolicyError('policy: unsupported version')
    entries = obj['entries']
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise PolicyError('policy: invalid entries or count limit exceeded')
    result, ids = [], set()
    for item in entries:
        if not isinstance(item, dict) or set(item) != {'planner_id', 'image_digest', 'platform', 'status'}:
            raise PolicyError('policy entry: invalid fields')
        pid, image, platform, status = (item[k] for k in ('planner_id', 'image_digest', 'platform', 'status'))
        if not isinstance(pid, str) or not _ID.fullmatch(pid):
            raise PolicyError('policy entry: invalid planner ID')
        if not isinstance(image, str) or not _DIGEST.fullmatch(image):
            raise PolicyError('policy entry: invalid image digest')
        if not isinstance(platform, str) or not _PLATFORM.fullmatch(platform):
            raise PolicyError('policy entry: invalid platform')
        if not isinstance(status, str) or status not in ('active', 'revoked'):
            raise PolicyError('policy entry: invalid status')
        if pid in ids:
            raise PolicyError('policy: duplicate planner ID')
        ids.add(pid)
        result.append(Entry(pid, image, platform, status))
    return Policy(tuple(result))


def load_policy(path) -> Policy:
    try:
        return parse_policy(read_bounded(path))
    except (OSError, SafeJSONError) as exc:
        raise PolicyError(f'cannot read policy: {exc}') from exc


def compare_policy(manifest: ManifestIdentity, policy: Policy) -> str:
    """Compare parsed claims; caller must not interpret MATCH as trusted admission."""
    for entry in policy.entries:
        if entry.planner_id == manifest.planner_id:
            if entry.status == 'revoked':
                return 'REVOKED'
            if entry.image_digest != manifest.image_digest or entry.platform != manifest.platform:
                return 'MISMATCH'
            return 'MATCH'
    return 'NOT_LISTED'
