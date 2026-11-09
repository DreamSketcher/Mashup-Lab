"""Isolated observation, not a render adapter or a qualification test.

Install pinned numpy, soxr and samplerate into a disposable environment; run
this script from that environment. This file does not import Mashup Lab.
"""
import hashlib
import json
import platform
import sys
import time

import numpy as np
import samplerate
import soxr


def expected(n, source, target):
    return (2 * n * target + source) // (2 * source)


def convert(name, x, source, target):
    if name == 'soxr':
        return soxr.resample(x, source, target, quality='HQ')
    return samplerate.resample(x, target / source, converter_type='sinc_best')


def stream(name, x, source, target, chunk):
    channels = 1 if x.ndim == 1 else x.shape[1]
    if name == 'soxr':
        s = soxr.ResampleStream(source, target, channels, dtype='float32', quality='HQ')
        def process(part, last):
            return s.resample_chunk(part, last=last)
    else:
        s = samplerate.Resampler(converter_type='sinc_best', channels=channels)
        def process(part, last):
            return s.process(part, target / source, end_of_input=last)
    pieces = [process(x[i:i + chunk], i + chunk >= len(x)) for i in range(0, len(x), chunk)]
    return np.concatenate(pieces), len(pieces[0])


def sha(x):
    return hashlib.sha256(np.asarray(x, dtype='<f4').tobytes()).hexdigest()


def run():
    n = 44100
    t = np.arange(n, dtype=np.float64) / 44100
    impulse = np.zeros(n, dtype=np.float32)
    impulse[5000] = 1
    fixtures = {'silence': np.zeros(n, np.float32), 'impulse': impulse,
                'dc': np.ones(n, dtype=np.float32),
                'sweep': (0.5 * np.sin(2 * np.pi * (100 * t + (20000 - 100) * t * t / 2))).astype(np.float32),
                'tone_1000': (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32),
                'stereo': np.column_stack(((0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32),
                                           (0.25 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)))}
    results = {}
    for name in ('soxr', 'samplerate'):
        info = {}
        for case, x in fixtures.items():
            y = convert(name, x, 44100, 48000)
            repeat = convert(name, x, 44100, 48000)
            item = {'input_frames': len(x), 'output_frames': len(y), 'expected_frames': expected(len(x), 44100, 48000),
                    'finite': bool(np.isfinite(y).all()), 'sha256_float32_le': sha(y),
                    'repeat_exact': bool(np.array_equal(y, repeat)),
                    'peak': float(np.max(np.abs(y)))}
            if case == 'dc':
                item['first_five'] = y[:5].tolist()
                item['last_five'] = y[-5:].tolist()
                item['interior_max_error'] = float(np.max(np.abs(y[2048:-2048] - 1)))
            if case == 'impulse':
                item['peak_frame'] = int(np.argmax(np.abs(y)))
                item['ideal_nearest_frame'] = expected(5000, 44100, 48000)
            if case == 'stereo':
                item['channel_ratio_max_error'] = float(np.max(np.abs(y[:, 1] - 0.5 * y[:, 0])))
            if case == 'tone_1000':
                # Same input, fresh instances, three chunk sizes and explicit EOS.
                item['stream'] = {}
                for size in (127, 1024, 4096):
                    try:
                        z, first = stream(name, x, 44100, 48000, size)
                        item['stream'][str(size)] = {'frames': len(z), 'first_output_frames': first,
                            'max_abs_diff': float(np.max(np.abs(y - z))) if len(z) == len(y) else None,
                            'exact': bool(np.array_equal(y, z))}
                    except Exception as exc:
                        item['stream'][str(size)] = {'error': str(exc)}
            info[case] = item
        # Compare a crop processed alone to the same interval in full context.
        full = fixtures['tone_1000']
        whole = convert(name, full, 44100, 48000)
        crop = convert(name, full[11025:33075], 44100, 48000)
        reference = whole[12000:12000 + len(crop)]
        delta = np.abs(crop - reference)
        info['context'] = {'crop_frames': len(crop), 'max_abs_diff': float(np.max(delta)),
                           'first_256_max_abs_diff': float(np.max(delta[:256])),
                           'interior_max_abs_diff': float(np.max(delta[2048:-2048]))}
        info['short_lengths'] = {}
        for length in (1, 2, 3, 10, 100, 441):
            y = convert(name, np.ones(length, dtype=np.float32), 44100, 48000)
            info['short_lengths'][str(length)] = {'frames': len(y), 'expected': expected(length, 44100, 48000)}
        # Linear system input whose 18 kHz aliases to 14 kHz after 48->32 kHz;
        # measure 14 kHz sinusoidal component excluding boundary transients.
        t = np.arange(48000, dtype=np.float64) / 48000
        down = (0.5 * np.sin(2 * np.pi * 18000 * t)).astype(np.float32)
        y = convert(name, down, 48000, 32000)
        a = y[2048:-2048].astype(np.float64)
        phase = 2 * np.pi * 14000 * np.arange(2048, len(y) - 2048) / 32000
        amp = 2 * np.hypot(np.dot(a, np.cos(phase)), np.dot(a, np.sin(phase))) / len(a)
        info['downsample_18k'] = {'frames': len(y), 'alias_amplitude_at_14k': float(amp),
                                  'alias_db_relative_to_input_peak': float(20 * np.log10(max(amp, 1e-30) / 0.5))}
        x = np.tile(fixtures['tone_1000'], 5)
        times = []
        for _ in range(5):
            begin = time.perf_counter(); convert(name, x, 44100, 48000); times.append(time.perf_counter() - begin)
        info['timing'] = {'seconds_input': 5, 'median_wall_s': float(np.median(times)), 'runs': len(times)}
        results[name] = info
    return {'python': sys.version.split()[0], 'platform': platform.platform(), 'numpy': np.__version__,
            'python_soxr': soxr.__version__, 'libsoxr': soxr.__libsoxr_version__,
            'python_samplerate': samplerate.__version__, 'libsamplerate': samplerate.__libsamplerate_version__,
            'results': results}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2, sort_keys=True))
