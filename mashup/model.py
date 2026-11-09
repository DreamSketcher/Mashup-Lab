"""Strict project parsing and exact, backend-independent timeline calculations."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
import hashlib
import re
import wave

import yaml


class ProjectError(ValueError):
    """A malformed or incompatible project."""


class Loader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise ProjectError("YAML aliases are not supported")
        if self.peek_event().tag is not None:
            raise ProjectError("explicit YAML tags are not supported")
        return super().compose_node(parent, index)


def _mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str):
            raise ProjectError("mapping keys must be strings")
        if key in result:
            raise ProjectError(f"duplicate key: {key}")
        result[key] = loader.construct_object(value_node)
    return result


def _decimal(loader, node):
    text = loader.construct_scalar(node)
    # A deliberately restricted decimal syntax avoids YAML 1.1 sexagesimal,
    # infinities, NaNs, and loss of precision through a Python float.
    if not re.fullmatch(r"[-+]?(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?", text):
        raise ProjectError(f"unsupported decimal: {text}")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ProjectError(f"invalid decimal: {text}") from exc


def _int(loader, node):
    text = loader.construct_scalar(node)
    if not re.fullmatch(r"[-+]?(?:0|[1-9][0-9]*)", text):
        raise ProjectError(f"unsupported integer: {text}")
    return int(text)


Loader.add_constructor('tag:yaml.org,2002:int', _int)
Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)
Loader.add_constructor('tag:yaml.org,2002:float', _decimal)


def fields(obj, names, where):
    if not isinstance(obj, dict) or set(obj) != set(names):
        raise ProjectError(f"{where}: expected fields {', '.join(names)}")


def integer(value, where, low=None, high=None):
    if type(value) is not int or (low is not None and value < low) or (high is not None and value > high):
        raise ProjectError(f"{where}: invalid integer")
    return value


def number(value, where, low=None, high=None, positive=False):
    if type(value) is int:
        value = Decimal(value)
    if not isinstance(value, Decimal) or not value.is_finite() or (positive and value <= 0) or (low is not None and value < Decimal(str(low))) or (high is not None and value > Decimal(str(high))):
        raise ProjectError(f"{where}: invalid decimal number")
    return Fraction(value)


def identifier(value, where):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ProjectError(f"{where}: invalid ID")
    return value


def round_half_up(value):
    """Round a nonnegative rational to nearest integer, ties upward."""
    if value < 0:
        raise ValueError("negative value")
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


@dataclass(frozen=True)
class Clip:
    id: str
    start: int
    end: int


@dataclass(frozen=True)
class Plan:
    clips: tuple[Clip, ...]
    overlaps: tuple[tuple[str, str, int, int], ...]
    total_frames: int

    def to_dict(self):
        """Versioned, JSON-compatible timeline plan, in project clip order."""
        return {
            'plan_version': '0.1',
            'sample_rate': 48000,
            'clips': [dict(id=c.id, start_frame=c.start, end_frame=c.end,
                           duration_frames=c.end - c.start) for c in self.clips],
            'overlaps': [dict(first_clip_id=a, second_clip_id=b, start_frame=start,
                              end_frame=end, duration_frames=end - start)
                         for a, b, start, end in self.overlaps],
            'total_frames': self.total_frames,
        }


def load_project(path):
    try:
        with Path(path).open(encoding='utf-8') as f:
            return yaml.load(f, Loader=Loader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ProjectError(f"cannot read project: {exc}") from exc


def plan_project(project, project_dir, verify_sources=True):
    fields(project, ('schema_version', 'timeline', 'sources', 'clips', 'render'), 'project')
    if project['schema_version'] != '0.1':
        raise ProjectError('unsupported schema_version')
    t = project['timeline']
    fields(t, ('bpm', 'time_signature', 'ppq', 'sample_rate'), 'timeline')
    bpm = number(t['bpm'], 'bpm', positive=True)
    sig = t['time_signature']
    if not isinstance(sig, list) or len(sig) != 2:
        raise ProjectError('invalid time signature')
    numerator = integer(sig[0], 'numerator', 1)
    denominator = integer(sig[1], 'denominator', 1)
    if denominator not in (1, 2, 4, 8, 16):
        raise ProjectError('invalid time signature denominator')
    if integer(t['ppq'], 'ppq') != 960 or integer(t['sample_rate'], 'sample_rate') != 48000:
        raise ProjectError('unsupported timeline rate or ppq')
    rate = 48000
    ticks_per_beat = 960 * 4 // denominator
    fields(project['render'], ('bit_depth',), 'render')
    if integer(project['render']['bit_depth'], 'bit_depth') not in (16, 24):
        raise ProjectError('unsupported output bit depth')
    sources = {}
    if not isinstance(project['sources'], list):
        raise ProjectError('sources must be a list')
    root = Path(project_dir).resolve()
    for s in project['sources']:
        fields(s, ('id', 'path', 'sha256', 'sample_rate', 'channels', 'frames'), 'source')
        sid = identifier(s['id'], 'source id')
        if sid in sources:
            raise ProjectError(f'duplicate source id: {sid}')
        if not isinstance(s['path'], str) or not s['path'] or Path(s['path']).is_absolute():
            raise ProjectError('invalid source path')
        p = (root / s['path']).resolve()
        if not p.is_relative_to(root):
            raise ProjectError('source path escapes project directory')
        if not isinstance(s['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', s['sha256']):
            raise ProjectError('invalid SHA-256')
        integer(s['sample_rate'], 'source sample_rate', 1)
        integer(s['channels'], 'source channels', 1, 2)
        integer(s['frames'], 'source frames', 1)
        if verify_sources:
            try:
                with p.open('rb') as f:
                    digest = hashlib.file_digest(f, 'sha256').hexdigest()
                if digest != s['sha256']:
                    raise ProjectError(f'source hash mismatch: {sid}')
                with wave.open(str(p), 'rb') as w:
                    if w.getcomptype() != 'NONE' or w.getsampwidth() not in (2, 3, 4):
                        raise ProjectError(f'unsupported WAV format: {sid}')
                    if (w.getframerate(), w.getnchannels(), w.getnframes()) != (s['sample_rate'], s['channels'], s['frames']):
                        raise ProjectError(f'source metadata mismatch: {sid}')
                    # Detect truncated data, rather than trusting the header alone.
                    remaining = s['frames']
                    while remaining:
                        n = min(remaining, 65536)
                        if len(w.readframes(n)) != n * s['channels'] * w.getsampwidth():
                            raise ProjectError(f'truncated WAV: {sid}')
                        remaining -= n
            except (OSError, wave.Error, EOFError) as exc:
                raise ProjectError(f'cannot read source {sid}: {exc}') from exc
        sources[sid] = s
    if not isinstance(project['clips'], list) or not project['clips']:
        raise ProjectError('clips must be a nonempty list')
    clips, ids = [], set()
    for c in project['clips']:
        fields(c, ('id', 'source_id', 'source_range', 'position', 'processing'), 'clip')
        cid = identifier(c['id'], 'clip id')
        if cid in ids:
            raise ProjectError(f'duplicate clip id: {cid}')
        ids.add(cid)
        sid = identifier(c['source_id'], 'source_id')
        if sid not in sources:
            raise ProjectError(f'unknown source: {sid}')
        s = sources[sid]
        r = c['source_range']
        fields(r, ('start_frame', 'end_frame'), 'source_range')
        start = integer(r['start_frame'], 'start_frame', 0)
        end = integer(r['end_frame'], 'end_frame', 1, s['frames'])
        if start >= end:
            raise ProjectError('empty or reversed source range')
        pos = c['position']
        fields(pos, ('bar', 'beat', 'tick'), 'position')
        bar = integer(pos['bar'], 'bar', 1)
        beat = integer(pos['beat'], 'beat', 1, numerator)
        tick = integer(pos['tick'], 'tick', 0, ticks_per_beat - 1)
        tick_index = ((bar - 1) * numerator + beat - 1) * ticks_per_beat + tick
        timeline_start = round_half_up(Fraction(tick_index * 60 * rate, 960) / bpm)
        proc = c['processing']
        fields(proc, ('duration_ratio', 'pitch_semitones', 'gain_db', 'pan', 'fade_in_frames', 'fade_out_frames'), 'processing')
        ratio = number(proc['duration_ratio'], 'duration_ratio', '0.5', '2')
        integer(proc['pitch_semitones'], 'pitch_semitones', -12, 12)
        number(proc['gain_db'], 'gain_db', '-120', '24')
        number(proc['pan'], 'pan', '-1', '1')
        length = round_half_up(Fraction((end - start) * rate, s['sample_rate']) * ratio)
        if length == 0:
            raise ProjectError('processed clip has zero frames')
        integer(proc['fade_in_frames'], 'fade_in_frames', 0, length)
        integer(proc['fade_out_frames'], 'fade_out_frames', 0, length)
        clips.append(Clip(cid, timeline_start, timeline_start + length))
    overlaps = []
    for i, a in enumerate(clips):
        for b in clips[i + 1:]:
            left, right = max(a.start, b.start), min(a.end, b.end)
            if left < right:
                overlaps.append((a.id, b.id, left, right))
    return Plan(tuple(clips), tuple(overlaps), max(c.end for c in clips))
