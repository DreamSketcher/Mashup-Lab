"""Read-only BPM and key estimates from external libraries, never a renderer stage."""
import json
import math
from pathlib import Path
import sys


def analyze(path):
    import librosa
    import numpy as np
    from music_key_detector import detect_key

    source = Path(path).expanduser()
    if not source.is_file():
        raise ValueError('Аудиофайл не найден')
    # Analysis only: a limited excerpt, original sample rate, no resampling or
    # project changes. Long tracks and tempo/key changes are not fully covered.
    y, sr = librosa.load(str(source), sr=None, mono=True, duration=90)
    if not len(y) or not np.isfinite(y).all():
        raise ValueError('Аудиофайл пуст или содержит неконечные значения')
    duration = float(len(y) / sr)
    if duration < 3 or float(np.max(np.abs(y))) < 1e-5:
        return {'bpm': None, 'key': None, 'duration_seconds': duration,
                'note': 'Слишком короткий или тихий фрагмент для оценки.'}
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.asarray(tempo).reshape(-1)[0])
    if not math.isfinite(bpm) or bpm <= 0 or len(beats) < 2:
        bpm = None
    key = detect_key(str(source), max_duration=90)
    return {'bpm': bpm, 'key': {'name': key.key, 'mode': key.mode,
                                'ambiguous': bool(key.ambiguous),
                                'result_type': key.result_type, 'reason': key.reason},
            'duration_seconds': duration,
            'note': 'Оценка первых 90 секунд: BPM может отличаться в 2 раза; тональность может меняться.'}


def main():
    try:
        if len(sys.argv) != 2:
            raise ValueError('Укажите один путь к аудиофайлу')
        print(json.dumps(analyze(sys.argv[1]), ensure_ascii=True, allow_nan=False))
        return 0
    except Exception as exc:
        print(f'Ошибка анализа: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
