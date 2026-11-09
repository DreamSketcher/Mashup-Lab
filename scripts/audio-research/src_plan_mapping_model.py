"""Research-only planner/SRC mapping model, not a production implementation.

Geometry and mock API are independent of the actual planner and DSP libraries.
The interpolator below models dependencies on intermediate grid points only:
linear time remapping changes pitch and is NOT a time-stretch implementation.
"""
from dataclasses import dataclass
from fractions import Fraction
import importlib.util
import json
import math
from pathlib import Path

_spec = importlib.util.spec_from_file_location('src_grid_oracle', Path(__file__).with_name('src_grid_oracle.py'))
grid = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(grid)


def round_fraction(x):
    if x < 0:
        raise ValueError('nonnegative only')
    return (2 * x.numerator + x.denominator) // (2 * x.denominator)


def lengths(n, fs, ft, ratio):
    # Compute final directly, never round SRC duration before applying ratio.
    grid._validate(n, fs, ft)
    if not isinstance(ratio, Fraction) or ratio <= 0:
        raise ValueError('ratio must be a positive exact Fraction')
    q = Fraction(n * ft, fs)
    return round_fraction(q), round_fraction(q * ratio)


def support(final_frames, ratio):
    """Indices needed by this *hypothetical* linear m/r interpolator.

    Real pitch-preserving stretch algorithms can need different input, padding,
    phase and latency. For integer coordinate the upper weight is zero and no
    second frame is requested. This routine is deliberately bounded to examples.
    """
    if type(final_frames) is not int or final_frames < 0 or not isinstance(ratio, Fraction) or ratio <= 0:
        raise ValueError('bad count or ratio')
    needed = set()
    for m in range(final_frames):
        p = Fraction(m, 1) / ratio
        lower = p.numerator // p.denominator
        needed.add(lower)
        if p.denominator != 1:
            needed.add(lower + 1)
    return needed


class MappingError(ValueError):
    pass


@dataclass(frozen=True)
class MockOutput:
    # Values and exact target-grid coordinates are synthetic oracle facts,
    # NOT metadata from a real SRC or proof of quality/phase.
    coordinates: tuple
    frames: tuple
    proven_for_experiment: bool = True


def extract_required(output, required):
    """Select proved, exact grid values; no manufactured samples or relabeling."""
    if not output.proven_for_experiment or len(output.coordinates) != len(output.frames):
        raise MappingError('mapping not established')
    if len(set(output.coordinates)) != len(output.coordinates):
        raise MappingError('duplicate coordinates')
    if any(not isinstance(c, Fraction) or c.denominator != 1 for c in output.coordinates):
        raise MappingError('not aligned to intermediate grid')
    table = {c.numerator: frame for c, frame in zip(output.coordinates, output.frames)}
    if not set(required) <= table.keys():
        raise MappingError('required coordinate absent')
    return {i: table[i] for i in sorted(required)}


def mock_ideal_api(channels, fs, ft, indices):
    """Zero-extended ideal synthetic SRC; integer nonnegative coordinates only."""
    frames = tuple(tuple(grid.ideal_value(channel, i, fs, ft) for channel in channels)
                   for i in indices)
    return MockOutput(tuple(Fraction(i) for i in indices), frames)


def toy_stretch(intermediate, final_frames, ratio):
    # Exact output grid dependencies, numerical linear interpolation. For
    # ratio=1 this is the identity. This is NOT pitch-preserving time-stretch.
    wanted = extract_required(intermediate, support(final_frames, ratio))
    result = []
    for m in range(final_frames):
        p = Fraction(m, 1) / ratio
        lo = p.numerator // p.denominator
        alpha = float(p - lo)
        left = wanted[lo]
        if not alpha:
            result.append(left)
        else:
            right = wanted[lo + 1]
            result.append(tuple((1-alpha)*a + alpha*b for a,b in zip(left, right)))
    return result


def compare_counts(n, fs, ft, ratio):
    src_length, final = lengths(n, fs, ft, ratio)
    needed = support(final, ratio)
    return {'N': n, 'Fs': fs, 'Ft': ft, 'ratio': str(ratio),
            'nominal_src_nearest': src_length, 'plan_final': final,
            'nominal_vs_final': ('more' if src_length > final else
                                 'less' if src_length < final else 'equal'),
            'toy_required_count': len(needed),
            'toy_required_max': max(needed) if needed else None,
            'toy_missing_if_nominal_only': sorted(needed - set(range(src_length)))}


def main():
    cases = [(1, 44100, 48000, Fraction(1)), (2, 44100, 48000, Fraction(1)),
             (10, 44100, 48000, Fraction(1)), (441, 44100, 48000, Fraction(1)),
             (441, 44100, 48000, Fraction(24,25)),
             (441, 44100, 48000, Fraction(26,25)),
             (2, 48000, 48000, Fraction(1,2)),
             (2, 48000, 48000, Fraction(2)),
             (1, 96000, 48000, Fraction(1,2)),
             (1, 96000, 48000, Fraction(2))]
    print(json.dumps({'description': 'Hypothetical linear support only; not pitch-preserving time stretch',
                      'matrix': [compare_counts(*c) for c in cases]}, indent=2))


if __name__ == '__main__':
    main()
