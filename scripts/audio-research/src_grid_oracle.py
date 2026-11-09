"""Research-only exact SRC geometry and ideal zero-extended sinc reference.

No DSP backend, project imports or third-party dependencies. This models
hypothetical contracts, not the existing planner or a production adapter.
"""
from fractions import Fraction
import json
import math


def _validate(n, fs, ft):
    if any(type(x) is not int for x in (n, fs, ft)):
        raise TypeError('frame count and rates must be integers')
    if n < 0 or fs <= 0 or ft <= 0:
        raise ValueError('nonnegative frame count and positive rates required')


def half_up_length(n, fs, ft):
    """Nearest duration in output frames, ties toward positive infinity."""
    _validate(n, fs, ft)
    return (2 * n * ft + fs) // (2 * fs)


def interval_point_count(n, fs, ft):
    """Number of m>=0 with m*fs/ft < n (end exclusive)."""
    _validate(n, fs, ft)
    return (n * ft + fs - 1) // fs


def source_coordinate(m, fs, ft):
    _validate(0, fs, ft)
    if type(m) is not int or m < 0:
        raise ValueError('output index must be a nonnegative integer')
    return Fraction(m * fs, ft)


def geometry(n, fs, ft):
    _validate(n, fs, ft)
    length = half_up_length(n, fs, ft)
    count = interval_point_count(n, fs, ft)
    duration = Fraction(n, fs)
    end = Fraction(length, ft)
    return {'input_frames': n, 'source_rate': fs, 'target_rate': ft,
            'input_duration_s': str(duration), 'duration_rounded_frames': length,
            'point_count_frames': count, 'duration_error_s': str(end - duration),
            'rounded_output_end_s': str(end),
            'first_excluded_input_coordinate': str(source_coordinate(length, fs, ft)),
            'excluded_point_inside_input': length < count}


def mapping(target_frames, api_frames, api_origin_in_target_frames):
    """Diagnose an API result whose constant phase/origin is *already known*.

    api j is at output-grid coordinate origin+j. Exact-grid matches only; no
    delay compensation, resampling, trimming, padding, or provenance implied.
    """
    if type(target_frames) is not int or type(api_frames) is not int or min(target_frames, api_frames) < 0:
        raise ValueError('frame counts must be nonnegative integers')
    origin = Fraction(api_origin_in_target_frames)
    if origin.denominator != 1:
        return {'on_target_grid': False, 'matched': 0, 'missing': target_frames,
                'extra': api_frames, 'note': 'fractional origin: no exact-grid index matches'}
    start = origin.numerator
    matched = max(0, min(target_frames, start + api_frames) - max(0, start))
    return {'on_target_grid': True, 'matched': matched,
            'missing': target_frames - matched, 'extra': api_frames - matched,
            'note': 'coordinates assumed, not measured; no signal-quality claim'}


def ideal_value(samples, m, fs, ft):
    """Ideal brickwall low-pass, zero extension; float64 numerical evaluation.

    samples is one finite channel; output coordinates are exact fractions before
    conversion to floating point. Not a bit-exact oracle for finite DSP filters.
    """
    _validate(len(samples), fs, ft)
    pos = source_coordinate(m, fs, ft)
    cutoff = min(Fraction(1), Fraction(ft, fs))
    def sinc(x):
        return 1.0 if x == 0 else math.sin(math.pi * x) / (math.pi * x)
    return math.fsum(float(sample) * float(cutoff) * sinc(float(cutoff * (pos - k)))
                     for k, sample in enumerate(samples))


def main():
    cases = [geometry(n, fs, ft) for fs, ft in ((44100, 48000), (48000, 32000),
                                                (48000, 24000), (48000, 16000), (48000, 48000),
                                                (32000, 48000))
             for n in (0, 1, 2, 3, 10, 441)]
    examples = {'api_same_length_shifted_one': mapping(480, 480, 1),
                'api_early_one': mapping(480, 481, -1),
                'api_fractional_phase': mapping(480, 480, Fraction(1, 2)),
                'api_missing_last': mapping(11, 10, 0)}
    print(json.dumps({'cases': cases, 'hypothetical_api_mapping': examples}, indent=2))


if __name__ == '__main__':
    main()
