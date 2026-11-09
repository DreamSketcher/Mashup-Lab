"""Create a small two-source project and use the existing renderer.

This is a convenience front end, not an audio analysis or DSP backend.
"""
import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import wave

import yaml

from .model import ProjectError, load_project, plan_project


class ProjectDumper(yaml.SafeDumper):
    pass


def _decimal_representer(dumper, value):
    text = format(value, 'f')
    if '.' not in text:
        text += '.0'
    return dumper.represent_scalar('tag:yaml.org,2002:float', text)


ProjectDumper.add_representer(Decimal, _decimal_representer)


def decimal_arg(value):
    if len(value) > 32 or not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)', value):
        raise argparse.ArgumentTypeError('use an ordinary decimal number, e.g. 120 or -6.5')
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError('invalid decimal') from exc


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog='python -m mashup quick-mashup',
        description='Create a two-WAV project and render it with the experimental 48 kHz renderer.',
        epilog='Defaults: both full files start at bar 1 beat 1; no tempo or pitch adjustment. No automatic musical alignment.')
    parser.add_argument('audio1', type=Path, help='first 48 kHz mono/stereo integer PCM WAV')
    parser.add_argument('audio2', type=Path, help='second 48 kHz mono/stereo integer PCM WAV')
    parser.add_argument('--project-dir', required=True, type=Path, help='new directory for the project, copies of sources and mashup.wav')
    parser.add_argument('--bpm', type=decimal_arg, default=Decimal('120'), help='manual timeline BPM (default: 120; does not change audio tempo)')
    parser.add_argument('--bit-depth', choices=(16, 24), type=int, default=24, help='WAV output bit depth (default: 24)')
    parser.add_argument('--verify-repeat', action='store_true', help='render again in this environment and compare PCM hashes')
    for n in (1, 2):
        group = parser.add_argument_group(f'audio {n} clip (defaults: whole source at bar 1 beat 1)')
        group.add_argument(f'--start{n}', type=int, default=0, help='first input frame, inclusive (default: 0)')
        group.add_argument(f'--end{n}', type=int, help='last input frame, exclusive (default: end of source)')
        group.add_argument(f'--bar{n}', type=int, default=1, help='one-based 4/4 timeline bar (default: 1)')
        group.add_argument(f'--beat{n}', type=int, default=1, help='one-based beat 1–4 (default: 1)')
        group.add_argument(f'--tick{n}', type=int, default=0, help='zero-based tick 0–959 (default: 0)')
        group.add_argument(f'--gain{n}', type=decimal_arg, default=Decimal('0'), help='gain in dB, -120 to 24 (default: 0)')
        group.add_argument(f'--pan{n}', type=decimal_arg, default=Decimal('0'), help='balance from -1 left to 1 right (default: 0)')
        group.add_argument(f'--fade-in{n}', type=int, default=0, help='fade-in in output frames (default: 0)')
        group.add_argument(f'--fade-out{n}', type=int, default=0, help='fade-out in output frames (default: 0)')
    return parser.parse_args(argv)


def inspect_wav(path):
    try:
        with wave.open(str(path), 'rb') as wav:
            rate, channels, frames = wav.getframerate(), wav.getnchannels(), wav.getnframes()
            if rate != 48000:
                raise ProjectError(f'{path}: expected 48000 Hz PCM WAV; resampling is not supported')
            if channels not in (1, 2) or frames < 1 or wav.getcomptype() != 'NONE' or wav.getsampwidth() not in (2, 3, 4):
                raise ProjectError(f'{path}: expected nonempty mono/stereo 16, 24 or 32-bit integer PCM WAV')
            return {'sample_rate': rate, 'channels': channels, 'frames': frames}
    except (OSError, wave.Error, EOFError) as exc:
        raise ProjectError(f'cannot read WAV {path}: {exc}') from exc


def create_and_render(args):
    from .render import render

    input_paths = [args.audio1, args.audio2]
    # Validate source headers and user options before creating any directories.
    metadata = [inspect_wav(path) for path in input_paths]
    sources, clips = [], []
    for n, info in enumerate(metadata, 1):
        end = getattr(args, f'end{n}')
        end = info['frames'] if end is None else end
        sources.append({'id': f'audio{n}', 'path': f'sources/audio{n}.wav',
                        'sha256': '0' * 64, **info})
        clips.append({'id': f'clip{n}', 'source_id': f'audio{n}',
                      'source_range': {'start_frame': getattr(args, f'start{n}'), 'end_frame': end},
                      'position': {'bar': getattr(args, f'bar{n}'), 'beat': getattr(args, f'beat{n}'), 'tick': getattr(args, f'tick{n}')},
                      'processing': {'duration_ratio': 1, 'pitch_semitones': 0,
                                     'gain_db': getattr(args, f'gain{n}'), 'pan': getattr(args, f'pan{n}'),
                                     'fade_in_frames': getattr(args, f'fade_in{n}'), 'fade_out_frames': getattr(args, f'fade_out{n}')}})
    project = {'schema_version': '0.1',
               'timeline': {'bpm': args.bpm, 'time_signature': [4, 4], 'ppq': 960, 'sample_rate': 48000},
               'sources': sources, 'clips': clips, 'render': {'bit_depth': args.bit_depth}}
    # Reuse the existing planner's validation for all clip ranges and options.
    plan_project(project, args.project_dir, verify_sources=False)
    try:
        # Require a new directory to prevent overwriting user data.
        args.project_dir.mkdir()
        (args.project_dir / 'sources').mkdir()
        for path, source in zip(input_paths, sources):
            target = args.project_dir / source['path']
            with path.open('rb') as src, target.open('xb') as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            # If a source changed during copying, metadata/identity of the copied
            # file is authoritative; renderer checks it again before rendering.
            if inspect_wav(target) != {key: source[key] for key in ('sample_rate', 'channels', 'frames')}:
                raise ProjectError(f'{path}: WAV metadata changed while copying')
            with target.open('rb') as f:
                source['sha256'] = hashlib.file_digest(f, 'sha256').hexdigest()
        project_path = args.project_dir / 'project.yaml'
        with project_path.open('x', encoding='utf-8', newline='\n') as f:
            yaml.dump(project, f, Dumper=ProjectDumper, sort_keys=False, allow_unicode=True)
        # Parse the generated file and use the same validation/renderer as normal.
        plan = plan_project(load_project(project_path), project_path.parent)
        output = args.project_dir / 'mashup.wav'
        result = render(project_path, output)
        repeat = None
        if args.verify_repeat:
            with tempfile.TemporaryDirectory(prefix='mashup-repeat-') as tmp:
                again = render(project_path, Path(tmp) / 'repeat.wav')
            repeat = (result['pcm_sha256'] == again['pcm_sha256'] and
                      result['frames'] == again['frames'] and result['bit_depth'] == again['bit_depth'])
            if not repeat:
                raise ProjectError('repeat render PCM does not match; inspect the project and environment')
    except OSError as exc:
        raise ProjectError(f'cannot create project files: {exc}') from exc
    return {'project': str(project_path), 'output': str(output),
            'sources': [str(args.project_dir / source['path']) for source in sources],
            'plan': plan.to_dict(), 'render': result, 'repeat_pcm_match': repeat}


def main(argv):
    args = parse_args(argv)
    try:
        result = create_and_render(args)
    except ProjectError as exc:
        print(f'error: {exc}', file=sys.stderr)
        print('If a new project directory was created, it may contain partial files; inspect it before retrying.', file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0
