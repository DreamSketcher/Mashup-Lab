"""Synthetic-contract tests; neither the planner nor real DSP is imported."""
import importlib.util
from fractions import Fraction as F
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('src_mapping_model', Path(__file__).resolve().parents[1] / 'scripts/audio-research/src_plan_mapping_model.py')
# dataclass resolves module in sys.modules
import sys
model = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = model
spec.loader.exec_module(model)


class PlannerSrcResearchTests(unittest.TestCase):
    def test_plan_lengths_are_not_double_rounded(self):
        self.assertEqual(model.lengths(1, 96000, 48000, F(1, 2)), (1, 0))
        # Naively rounding intermediate 1 then multiplying by 2 gives 2, not 1.
        self.assertEqual(model.lengths(1, 96000, 48000, F(2)), (1, 1))
        self.assertEqual(model.lengths(441, 44100, 48000, F(24,25)), (480,461))
        self.assertEqual(model.lengths(441, 44100, 48000, F(26,25)), (480,499))

    def test_unity_known_mapping_and_tail_vs_missing(self):
        clip = [[1.0, 0.0, 0.0, -0.25]]
        ref = model.mock_ideal_api(clip, 44100, 48000, range(4))
        extra = model.mock_ideal_api(clip, 44100, 48000, range(6))
        self.assertEqual(model.toy_stretch(extra, 4, F(1)), list(ref.frames))
        missing = model.mock_ideal_api(clip, 44100, 48000, range(3))
        with self.assertRaisesRegex(model.MappingError, 'absent'):
            model.toy_stretch(missing, 4, F(1))
        shifted = model.MockOutput(tuple(F(i+1) for i in range(4)), ref.frames)
        with self.assertRaisesRegex(model.MappingError, 'absent'):
            model.toy_stretch(shifted, 4, F(1))
        fractional = model.MockOutput(tuple(F(2*i+1, 2) for i in range(4)), ref.frames)
        with self.assertRaisesRegex(model.MappingError, 'not aligned'):
            model.toy_stretch(fractional, 4, F(1))
        # Equal output length can also be made of *wrong* samples despite
        # convenient numeric labels: metadata alone isn't a physical proof.
        unproved = model.MockOutput(ref.coordinates, tuple(reversed(ref.frames)), False)
        with self.assertRaisesRegex(model.MappingError, 'not established'):
            model.toy_stretch(unproved, 4, F(1))
        with self.assertRaisesRegex(model.MappingError, 'not established'):
            model.toy_stretch(model.MockOutput(ref.coordinates, ref.frames, False), 4, F(1))
        with self.assertRaisesRegex(model.MappingError, 'duplicate'):
            model.extract_required(model.MockOutput((F(0), F(0)), ((1.0,), (1.0,))), {0})

    def test_ratio_support_is_not_plan_final_or_src_length(self):
        src, final = model.lengths(441, 44100, 48000, F(26,25))
        required = model.support(final, F(26,25))
        self.assertEqual((src,final), (480,499))
        self.assertEqual(max(required), 479)
        self.assertLess(len(required), final)
        src, final = model.lengths(2, 48000, 48000, F(2))
        required = model.support(final, F(2))
        self.assertEqual((src, final, required), (2, 4, {0, 1, 2}))
        clip = [[1.0, 0.0]]
        with self.assertRaises(model.MappingError):
            model.toy_stretch(model.mock_ideal_api(clip,48000,48000,range(2)), final, F(2))
        values = model.toy_stretch(model.mock_ideal_api(clip,48000,48000,range(3)), final, F(2))
        self.assertEqual(len(values), final)

    def test_shorter_final_can_still_need_more_intermediate_frames(self):
        src, final = model.lengths(441, 44100, 48000, F(24,25))
        required = model.support(final, F(24,25))
        self.assertEqual((src, final, max(required)), (480, 461, 480))
        # A synthetic ramp at every integer stage coordinate has known linear
        # interpolation at m/r. No assertion about a real stretch algorithm.
        frames = tuple((float(i),) for i in range(481))
        out = model.MockOutput(tuple(F(i) for i in range(481)), frames)
        with self.assertRaises(model.MappingError):
            model.toy_stretch(model.MockOutput(out.coordinates[:-1], out.frames[:-1]), final, F(24,25))
        values = model.toy_stretch(out, final, F(24,25))
        self.assertAlmostEqual(values[-1][0], float(F(460) / F(24,25)), places=12)

    def test_three_independent_clips_context_stereo_and_placement(self):
        # Two sources differ outside selected ranges. No state crosses clips.
        clips = [([0.0, 0.0, 1.0, 0.0], 0),
                 ([0.5, 0.5], 5), ([-1.0, 0.0, 0.0], 9)]
        render = []
        for clip, start in clips:
            sources = [[42.0, 43.0] + clip + [88.0], [-91.0, -92.0] + clip + [-99.0]]
            outputs = []
            for source in sources:
                selected = source[2:2+len(clip)]
                channels = [selected, [-x/2 for x in selected]]
                length = model.lengths(len(clip), 44100, 48000, F(1))[1]
                output = model.mock_ideal_api(channels, 44100, 48000, range(length+1))
                outputs.append(model.toy_stretch(output, length, F(1)))
            self.assertEqual(outputs[0], outputs[1])
            for left,right in outputs[0]:
                self.assertAlmostEqual(right, -left/2, places=14)
            render.append((start, outputs[0]))
        # Independent timeline placement as prescribed by a synthetic plan.
        result = [(0.0,0.0)] * 13
        for start, values in render:
            result[start:start+len(values)] = values
        self.assertEqual(result[4], (0.0, 0.0))
        self.assertEqual(result[8], (0.0, 0.0))
        self.assertEqual(len(result), 13)
        self.assertGreater(result[2][0], 0.0)  # impulse contributes on the local grid

    def test_zero_length_is_mathematically_defined_not_validated_project(self):
        self.assertEqual(model.lengths(0, 44100, 48000, F(1)), (0,0))
        self.assertEqual(model.support(0, F(1)), set())
        self.assertEqual(model.toy_stretch(model.MockOutput((), ()), 0, F(1)), [])


if __name__ == '__main__':
    unittest.main()
