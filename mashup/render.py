"""Experimental fixed-rate, identity-transform PCM renderer (in-memory)."""
import hashlib
import io
from pathlib import Path
import wave

import numpy as np
import soundfile as sf

from .model import ProjectError, load_project, plan_project
from .plan_validation import validate_plan


def render(project_path, output_path, trace=None):
    def emit(event, **fields):
        if trace is not None:
            trace(event, **fields)

    emit('render.start', project=str(project_path), output=str(output_path))
    project_path = Path(project_path)
    project = load_project(project_path)
    # Validate all structure and calculate the plan from this exact project object.
    plan = plan_project(project, project_path.parent, verify_sources=False)
    validate_plan(plan.to_dict())
    emit('render.plan_validated', frames=plan.total_frames, clips=len(plan.clips), overlaps=len(plan.overlaps))
    for clip in project['clips']:
        proc = clip['processing']
        if proc['duration_ratio'] != 1 or proc['pitch_semitones'] != 0:
            raise ProjectError(f"clip {clip['id']}: stretch and pitch shift are not supported")
    sources = {}
    root = project_path.parent.resolve()
    for source in project['sources']:
        sid = source['id']
        emit('render.source_start', source_id=sid, frames=source['frames'], channels=source['channels'])
        if source['sample_rate'] != 48000:
            raise ProjectError(f'source {sid}: resampling is not supported; 48000 Hz required')
        try:
            # Hash, validate and decode the same immutable bytes, not separate reads.
            data = (root / source['path']).resolve().read_bytes()
            if hashlib.sha256(data).hexdigest() != source['sha256']:
                raise ProjectError(f'source hash mismatch: {sid}')
            with wave.open(io.BytesIO(data), 'rb') as wav:
                if wav.getcomptype() != 'NONE' or wav.getsampwidth() not in (2, 3, 4):
                    raise ProjectError(f'unsupported WAV format: {sid}')
                if (wav.getframerate(), wav.getnchannels(), wav.getnframes()) != (source['sample_rate'], source['channels'], source['frames']):
                    raise ProjectError(f'source metadata mismatch: {sid}')
                if len(wav.readframes(source['frames'])) != source['frames'] * source['channels'] * wav.getsampwidth():
                    raise ProjectError(f'truncated WAV: {sid}')
            samples, rate = sf.read(io.BytesIO(data), dtype='float64', always_2d=True)
            if rate != 48000 or samples.shape != (source['frames'], source['channels']):
                raise ProjectError(f'decoded source metadata mismatch: {sid}')
            if not np.isfinite(samples).all():
                raise ProjectError(f'non-finite samples: {sid}')
            sources[sid] = samples
            emit('render.source_decoded', source_id=sid, frames=len(samples))
        except (OSError, wave.Error, EOFError, sf.LibsndfileError) as exc:
            raise ProjectError(f'cannot read source {sid}: {exc}') from exc
    mix = np.zeros((plan.total_frames, 2), dtype=np.float64)
    for clip, bounds in zip(project['clips'], plan.clips):
        emit('render.clip_start', clip_id=clip['id'], start=bounds.start, end=bounds.end)
        p = clip['processing']
        r = clip['source_range']
        samples = sources[clip['source_id']][r['start_frame']:r['end_frame']].copy()
        if samples.shape[1] == 1:
            samples = np.repeat(samples, 2, axis=1)
        if len(samples) != bounds.end - bounds.start:
            raise ProjectError(f"clip {clip['id']}: plan length mismatch")
        gain = 10.0 ** (float(p['gain_db']) / 20.0)
        pan = float(p['pan'])
        samples *= np.array([gain * (1 - max(pan, 0)), gain * (1 + min(pan, 0))])
        n = p['fade_in_frames']
        if n:
            samples[:n] *= (np.arange(1, n + 1, dtype=np.float64) / n)[:, None]
        n = p['fade_out_frames']
        if n:
            samples[-n:] *= (np.arange(n, 0, -1, dtype=np.float64) / n)[:, None]
        mix[bounds.start:bounds.end] += samples
        if not np.isfinite(mix[bounds.start:bounds.end]).all():
            raise ProjectError(f"clip {clip['id']}: non-finite mix")
        emit('render.clip_mixed', clip_id=clip['id'], frames=len(samples))
    peak = float(np.max(np.abs(mix)))
    scale = 1.0 / peak if peak > 1 else 1.0
    mix *= scale
    emit('render.peak', peak=peak, scale=scale)
    bits = project['render']['bit_depth']
    scaled = mix * (2 ** (bits - 1))
    quantized = np.clip(np.copysign(np.floor(np.abs(scaled) + 0.5), scaled), -(2 ** (bits - 1)), 2 ** (bits - 1) - 1).astype(np.int32)
    if bits == 16:
        pcm = quantized.astype('<i2').tobytes()
    else:
        flat = quantized.ravel()
        packed = np.empty((flat.size, 3), dtype=np.uint8)
        for byte in range(3):
            packed[:, byte] = (flat >> (8 * byte)) & 255
        pcm = packed.tobytes()
    # Exclusive creation prevents overwriting the project, sources or any output.
    try:
        with Path(output_path).open('xb') as out:
            with wave.open(out, 'wb') as wav:
                wav.setnchannels(2)
                wav.setsampwidth(bits // 8)
                wav.setframerate(48000)
                wav.writeframes(pcm)
    except OSError as exc:
        raise ProjectError(f'cannot create output: {exc}') from exc
    result = {'frames': plan.total_frames, 'peak': peak, 'scale': scale,
              'pcm_sha256': hashlib.sha256(pcm).hexdigest(), 'bit_depth': bits}
    emit('render.complete', **result)
    return result
