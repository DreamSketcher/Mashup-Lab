"""Validate a derived timeline plan independently of project calculation."""
import json
import re
from pathlib import Path

from .model import ProjectError


def _object(value, keys, name):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ProjectError(f'{name}: expected fields {", ".join(keys)}')


def _frame(value, name):
    if type(value) is not int or value < 0:
        raise ProjectError(f'{name}: expected nonnegative integer')
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProjectError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ProjectError(f'invalid JSON constant: {value}')


def load_plan(path):
    try:
        with Path(path).open(encoding='utf-8') as f:
            return json.load(f, object_pairs_hook=_unique_object,
                             parse_constant=_invalid_constant)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, ProjectError):
            raise
        raise ProjectError(f'cannot read plan: {exc}') from exc


def validate_plan(plan):
    """Check geometry, completeness and order without access to the project.

    This does not prove that a plan corresponds to a project or source files.
    """
    _object(plan, ('plan_version', 'sample_rate', 'clips', 'overlaps', 'total_frames'), 'plan')
    if plan['plan_version'] != '0.1':
        raise ProjectError('unsupported plan version')
    if type(plan['sample_rate']) is not int or plan['sample_rate'] != 48000:
        raise ProjectError('unsupported plan sample rate')
    clips = plan['clips']
    if not isinstance(clips, list) or not clips:
        raise ProjectError('plan clips must be a nonempty list')
    by_id = set()
    for clip in clips:
        _object(clip, ('id', 'start_frame', 'end_frame', 'duration_frames'), 'clip')
        if not isinstance(clip['id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]+', clip['id']):
            raise ProjectError('invalid clip ID')
        if clip['id'] in by_id:
            raise ProjectError('duplicate clip ID')
        by_id.add(clip['id'])
        start = _frame(clip['start_frame'], 'clip start_frame')
        end = _frame(clip['end_frame'], 'clip end_frame')
        duration = _frame(clip['duration_frames'], 'clip duration_frames')
        if start >= end or duration != end - start:
            raise ProjectError('invalid clip interval or duration')
    if _frame(plan['total_frames'], 'total_frames') != max(c['end_frame'] for c in clips):
        raise ProjectError('invalid total_frames')
    overlaps = plan['overlaps']
    if not isinstance(overlaps, list):
        raise ProjectError('overlaps must be a list')
    for overlap in overlaps:
        _object(overlap, ('first_clip_id', 'second_clip_id', 'start_frame', 'end_frame', 'duration_frames'), 'overlap')
        for name in ('first_clip_id', 'second_clip_id'):
            if not isinstance(overlap[name], str) or overlap[name] not in by_id:
                raise ProjectError('overlap references unknown clip')
        for name in ('start_frame', 'end_frame', 'duration_frames'):
            _frame(overlap[name], f'overlap {name}')
    # Independently derive the complete ordered set of pairwise intersections.
    # Equality checks boundaries, durations, clip ordering, missing and extra pairs.
    expected = []
    for i, a in enumerate(clips):
        for b in clips[i + 1:]:
            start = max(a['start_frame'], b['start_frame'])
            end = min(a['end_frame'], b['end_frame'])
            if start < end:
                expected.append({'first_clip_id': a['id'], 'second_clip_id': b['id'],
                                 'start_frame': start, 'end_frame': end,
                                 'duration_frames': end - start})
    if overlaps != expected:
        raise ProjectError('overlaps do not match ordered clip intersections')
