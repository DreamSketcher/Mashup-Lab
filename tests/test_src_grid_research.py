"""Tests of a research model only; these do not test or change renderer rules."""
import importlib.util
import math
from fractions import Fraction
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'scripts/audio-research/src_grid_oracle.py'
spec = importlib.util.spec_from_file_location('src_grid_oracle_research', path)
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)


class SrcGeometryResearchTests(unittest.TestCase):
    def test_known_small_cases(self):
        cases = [(0, 44100, 48000, 0, 0), (1, 44100, 48000, 1, 2),
                 (2, 44100, 48000, 2, 3), (1, 48000, 24000, 1, 1),
                 (1, 48000, 32000, 1, 1), (2, 48000, 32000, 1, 2),
                 (1, 48000, 16000, 0, 1), (2, 32000, 48000, 3, 3),
                 (10, 44100, 48000, 11, 11)]
        for n, fs, ft, rounded, count in cases:
            with self.subTest(n=n, fs=fs, ft=ft):
                self.assertEqual(oracle.half_up_length(n, fs, ft), rounded)
                self.assertEqual(oracle.interval_point_count(n, fs, ft), count)

    def test_point_count_from_independent_enumeration(self):
        for fs in range(1, 14):
            for ft in range(1, 14):
                for n in range(9):
                    actual = sum(Fraction(m, ft) < Fraction(n, fs)
                                 for m in range(n * ft + 1))
                    self.assertEqual(oracle.interval_point_count(n, fs, ft), actual)
                    rounded = oracle.half_up_length(n, fs, ft)
                    self.assertIn(actual - rounded, (0, 1))
                    # Nearest duration; ties toward larger nonnegative count.
                    self.assertLessEqual(abs(Fraction(rounded, ft) - Fraction(n, fs)), Fraction(1, 2*ft))
                    if abs(Fraction(rounded, ft) - Fraction(n, fs)) == Fraction(1, 2*ft):
                        self.assertGreaterEqual(Fraction(rounded, ft), Fraction(n, fs))

    def test_rate_scaling_and_boundaries(self):
        for n in (0, 1, 2, 17, 10**20):
            self.assertEqual(oracle.half_up_length(n, 44100, 48000), oracle.half_up_length(n, 441000, 480000))
            self.assertEqual(oracle.interval_point_count(n, 44100, 48000), oracle.interval_point_count(n, 441000, 480000))
        self.assertEqual(oracle.source_coordinate(1, 44100, 48000), Fraction(147, 160))
        self.assertEqual(oracle.source_coordinate(480, 44100, 48000), 441)
        self.assertEqual(oracle.geometry(1, 44100, 48000)['duration_error_s'], '-13/7056000')

    def test_input_validation(self):
        for args in [(-1, 1, 1), (1, 0, 1), (1, 1, 0), (1, -1, 1)]:
            with self.assertRaises(ValueError):
                oracle.geometry(*args)
        for args in [(1.0, 1, 1), (True, 1, 1), (1, 1.0, 1)]:
            with self.assertRaises(TypeError):
                oracle.geometry(*args)

    def test_mapping_not_just_equal_length(self):
        self.assertEqual(oracle.mapping(480, 480, 1)['missing'], 1)
        self.assertEqual(oracle.mapping(480, 480, 1)['extra'], 1)
        self.assertEqual(oracle.mapping(480, 481, -1)['missing'], 0)
        self.assertEqual(oracle.mapping(480, 481, -1)['extra'], 1)
        self.assertFalse(oracle.mapping(480, 480, Fraction(1, 2))['on_target_grid'])
        self.assertEqual(oracle.mapping(11, 10, 0)['missing'], 1)
        self.assertEqual(oracle.mapping(0, 0, 0)['matched'], 0)

    def test_ideal_impulse_and_linearity(self):
        self.assertEqual(oracle.ideal_value([1.0], 0, 44100, 48000), 1.0)
        self.assertAlmostEqual(oracle.ideal_value([1.0], 0, 48000, 32000), 2/3, places=15)
        self.assertAlmostEqual(oracle.ideal_value([0.0, 1.0], 1, 44100, 48000),
                               math.sin(math.pi * float(Fraction(-13,160))) / (math.pi * float(Fraction(-13,160))), places=15)
        a, b = [0.25, -0.5, 0.75], [-0.4, 0.1, 0.2]
        for m in range(4):
            total = oracle.ideal_value([x+y for x,y in zip(a,b)], m, 44100, 48000)
            self.assertAlmostEqual(total, oracle.ideal_value(a,m,44100,48000) + oracle.ideal_value(b,m,44100,48000), places=14)
        self.assertEqual(oracle.ideal_value([], 0, 44100, 48000), 0.0)


if __name__ == '__main__':
    unittest.main()
