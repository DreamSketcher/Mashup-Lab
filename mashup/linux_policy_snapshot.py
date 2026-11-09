"""Fail-closed placeholder for future Linux trusted policy snapshots.

This module does not open paths, verify filesystem properties, take locks, read
policy bytes, or establish trust. It is intentionally not wired into the CLI.
"""
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class SnapshotStatus(str, Enum):
    UNAVAILABLE = 'UNAVAILABLE'


@dataclass(frozen=True)
class SnapshotResult:
    """No bytes or authorization are returned by the unimplemented adapter."""
    status: SnapshotStatus
    reason: str


def capture_policy_snapshot(configured_policy_path: Path) -> SnapshotResult:
    """Always fail closed until a supported adapter and its tests exist.

    The argument is an API placeholder, not proof that the path is trusted.
    Future code must obtain it from protected installation configuration, not
    untrusted requests. Do not treat this result as a policy or admission check.
    """
    return SnapshotResult(
        status=SnapshotStatus.UNAVAILABLE,
        reason='Linux trusted policy snapshot adapter is not implemented',
    )
