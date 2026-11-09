"""Research harness: compare pinned wrapper and separately built native API.

Requires numpy, samplerate, soxr in an isolated venv and LIBSAMPLERATE_SO
pointing to a separately built libsamplerate 0.2.2 shared library. This is not
an adapter, and native library is not assumed to equal the wheel's build.
"""
import ctypes as C
import hashlib
import json
import os
import platform
import sys

import numpy as np
import samplerate
import soxr

F = C.POINTER(C.c_float)
class Data(C.Structure):
    _fields_ = [('data_in', F), ('data_out', F), ('input_frames', C.c_long),
                ('output_frames', C.c_long), ('input_frames_used', C.c_long),
                ('output_frames_gen', C.c_long), ('end_of_input', C.c_int),
                ('src_ratio', C.c_double)]

lib = C.CDLL(os.environ['LIBSAMPLERATE_SO'])
lib.src_new.argtypes = [C.c_int, C.c_int, C.POINTER(C.c_int)]
lib.src_new.restype = C.c_void_p
lib.src_process.argtypes = [C.c_void_p, C.POINTER(Data)]
lib.src_process.restype = C.c_int
lib.src_simple.argtypes = [C.POINTER(Data), C.c_int, C.c_int]
lib.src_simple.restype = C.c_int
lib.src_delete.argtypes = [C.c_void_p]
lib.src_delete.restype = C.c_void_p
lib.src_strerror.argtypes = [C.c_int]
lib.src_strerror.restype = C.c_char_p


def invoke(state, x, ratio, cap, eos, simple=False):
    out = np.zeros((cap, x.shape[1]), dtype=np.float32)
    d = Data(x.ctypes.data_as(F), out.ctypes.data_as(F), len(x), cap, 0, 0, eos, ratio)
    err = lib.src_simple(C.byref(d), 0, x.shape[1]) if simple else lib.src_process(state, C.byref(d))
    if err:
        raise RuntimeError(lib.src_strerror(err).decode())
    return out[:d.output_frames_gen].copy(), d.input_frames_used


def native(x, ratio, chunk, cap):
    error = C.c_int()
    state = lib.src_new(0, x.shape[1], C.byref(error))  # SRC_SINC_BEST_QUALITY
    if not state:
        raise RuntimeError(lib.src_strerror(error.value).decode())
    pieces, calls, consumed = [], [], 0
    try:
        for start in range(0, len(x), chunk):
            block = x[start:start + chunk]
            offset = 0
            eos = start + len(block) == len(x)
            while offset < len(block):
                y, used = invoke(state, block[offset:], ratio, cap, eos)
                calls.append([len(block) - offset, used, len(y), int(eos)])
                pieces.append(y); offset += used; consumed += used
                if used == 0 and not len(y):
                    raise RuntimeError('no progress with unconsumed input')
        # Drain without manufacturing input. Stop at first zero output.
        empty = np.empty((0, x.shape[1]), dtype=np.float32)
        for _ in range(10000):
            y, used = invoke(state, empty, ratio, cap, True)
            calls.append([0, used, len(y), 1]); pieces.append(y)
            if not len(y):
                break
        else:
            raise RuntimeError('drain did not terminate')
    finally:
        lib.src_delete(state)
    return np.concatenate(pieces), calls, consumed


def emulate_wrapper(x, ratio, chunk):
    """Expose counters with the buffer size and one-call policy of v0.2.4."""
    error = C.c_int()
    state = lib.src_new(0, x.shape[1], C.byref(error))
    if not state:
        raise RuntimeError(lib.src_strerror(error.value).decode())
    pieces, calls = [], []
    try:
        for start in range(0, len(x), chunk):
            block = x[start:start+chunk]
            cap = int(np.ceil(len(block) * ratio))
            y, used = invoke(state, block, ratio, cap, start+chunk >= len(x))
            pieces.append(y); calls.append({'offered': len(block), 'used': used,
                                           'capacity': cap, 'generated': len(y),
                                           'eos': start+chunk >= len(x)})
        tail = []
        empty = np.empty((0, x.shape[1]), dtype=np.float32)
        for _ in range(10000):
            y, _ = invoke(state, empty, ratio, 256, True)
            if not len(y):
                break
            tail.append(y)
        else:
            raise RuntimeError('drain did not terminate')
    finally:
        lib.src_delete(state)
    return np.concatenate(pieces), calls, np.concatenate(tail) if tail else empty


def metrics(y, ref):
    length = min(len(y), len(ref))
    return {'frames': len(y), 'reference_frames': len(ref),
            'prefix_max_abs_diff': float(np.max(np.abs(y[:length] - ref[:length]))) if length else None,
            'exact': bool(np.array_equal(y, ref))}


def run():
    report = {}
    for source, target in [(44100, 48000), (48000, 32000)]:
        ratio = target / source
        for channels in (1, 2):
            for n in (1, 10, 100, 441, 4096):
                for kind in ('first_impulse', 'last_impulse', 'tone'):
                    x = np.zeros((n, channels), np.float32)
                    if kind == 'tone':
                        x[:, 0] = np.sin(2*np.pi*997*np.arange(n)/source) * 0.5
                    else:
                        x[0 if kind == 'first_impulse' else -1, 0] = 1
                    if channels == 2:
                        x[:, 1] = -0.5*x[:, 0]
                    shape = x[:, 0] if channels == 1 else x
                    expected = (2*n*target + source)//(2*source)
                    simple, simple_used = invoke(None, x, ratio, max(1024, n*3+1024), 1, True)
                    wrapped = samplerate.resample(shape, ratio, converter_type='sinc_best').reshape(-1, channels)
                    sx = soxr.resample(shape, source, target, quality='HQ').reshape(-1, channels)
                    # Analytical ideal, infinite sinc reconstruction of a finite zero-extended
                    # input. It is an illustrative oracle, not these finite filters' spec.
                    oracle = None
                    if kind != 'tone':
                        k = 0 if kind == 'first_impulse' else n - 1
                        m = min(expected - 1, (2*k*target + source)//(2*source))
                        cutoff = min(1.0, target/source)
                        ideal = cutoff * np.sinc(cutoff * (m*source/target - k))
                        oracle = {'input_impulse_frame': k, 'output_frame': m,
                                  'input_coordinate': m*source/target,
                                  'ideal_sinc_value': float(ideal),
                                  'native_value': float(simple[m, 0]) if m < len(simple) else None,
                                  'soxr_value': float(sx[m, 0]) if m < len(sx) else None}
                    rec = {'geometry_half_up': expected, 'ideal_impulse_probe': oracle, 'native_simple_used': simple_used,
                           'wrapper_vs_native_simple': metrics(wrapped, simple),
                           'soxr_frames': len(sx), 'streams': {}}
                    for chunk in (1, 127, 1024):
                        sy, calls, consumed = native(x, ratio, chunk, 256)
                        sr = samplerate.Resampler('sinc_best', channels)
                        parts = [sr.process(shape[i:i+chunk], ratio, end_of_input=i+chunk>=n).reshape(-1,channels)
                                 for i in range(0,n,chunk)]
                        wy = np.concatenate(parts)
                        ss = soxr.ResampleStream(source, target, channels, dtype='float32', quality='HQ')
                        sz = np.concatenate([ss.resample_chunk(shape[i:i+chunk], last=i+chunk>=n).reshape(-1,channels)
                                             for i in range(0,n,chunk)])
                        rec['streams'][str(chunk)] = {'native_vs_simple': metrics(sy, simple),
                            'native_consumed': consumed, 'native_calls': len(calls),
                            'native_partial_input_calls': sum(a > b for a,b,_,_ in calls),
                            'native_drain_generated': sum(c for a,_,c,_ in calls if a == 0),
                            'wrapper_vs_native': metrics(wy, sy), 'soxr_vs_oneshot': metrics(sz, sx)}
                    report[f'{source}-{target}-ch{channels}-n{n}-{kind}'] = rec
    # Deliberately different context and a start not aligned to the output grid.
    # Only crop is passed to the converter, with fresh state for each call.
    start, n = 137, 441
    rng = np.random.default_rng(2026)
    clip = rng.standard_normal(n, dtype=np.float32) * 0.1
    contexts = [np.zeros(start+n+200, np.float32), rng.standard_normal(start+n+200, dtype=np.float32)]
    for context in contexts:
        context[start:start+n] = clip
    independence = {}
    for name, fn in [('soxr', lambda a: soxr.resample(a, 44100, 48000, quality='HQ')),
                     ('samplerate', lambda a: samplerate.resample(a, 48000/44100, converter_type='sinc_best'))]:
        a, b = [fn(context[start:start+n].copy()) for context in contexts]
        independence[name] = {'exact': bool(np.array_equal(a,b)), 'frames': len(a),
                              'input_start': start, 'input_end_exclusive': start+n}
    n, chunk, ratio = 44100, 1024, 48000/44100
    x = (0.5*np.sin(2*np.pi*1000*np.arange(n)/44100)).astype(np.float32).reshape(-1, 1)
    emulated, calls, tail = emulate_wrapper(x, ratio, chunk)
    sr = samplerate.Resampler('sinc_best', 1)
    actual = np.concatenate([sr.process(x[i:i+chunk], ratio, end_of_input=i+chunk>=n)
                             for i in range(0,n,chunk)])
    full, native_calls, used = native(x, ratio, chunk, 256)
    wrapper_trace = {'emulated_vs_wrapper': metrics(emulated, actual),
                     'emulated_vs_native_complete': metrics(emulated, full),
                     'tail_frames': len(tail),
                     'with_native_tail_vs_complete': metrics(np.concatenate((emulated, tail)), full),
                     'all_input_consumed': sum(c['used'] for c in calls),
                     'partial_calls': sum(c['used'] < c['offered'] for c in calls),
                     'last_call': calls[-1], 'calls': calls,
                     'native_complete_input_consumed': used,
                     'native_complete_drain_generated': sum(c for a,_,c,_ in native_calls if a == 0)}
    return {'wrapper_capacity_trace': wrapper_trace, 'context_isolation_crop_first': independence, 'environment': {'python': sys.version, 'platform': platform.platform(), 'numpy': np.__version__,
             'samplerate': samplerate.__version__, 'wheel_libsamplerate': samplerate.__libsamplerate_version__,
             'soxr': soxr.__version__, 'libsoxr': soxr.__libsoxr_version__,
             'native_sha256': hashlib.sha256(open(os.environ['LIBSAMPLERATE_SO'], 'rb').read()).hexdigest()},
            'cases': report}

if __name__ == '__main__':
    print(json.dumps(run(), indent=2, sort_keys=True))
