import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mashup.model import ProjectError
from mashup.plan_validation import load_plan, validate_plan


def example():
    # Deliberately not ordered by time or ID.
    return {
        'plan_version': '0.1', 'sample_rate': 48000,
        'clips': [
            {'id': 'z', 'start_frame': 10, 'end_frame': 20, 'duration_frames': 10},
            {'id': 'a', 'start_frame': 0, 'end_frame': 15, 'duration_frames': 15},
            {'id': 'b', 'start_frame': 10, 'end_frame': 20, 'duration_frames': 10},
            {'id': 'alone', 'start_frame': 20, 'end_frame': 21, 'duration_frames': 1},
        ],
        'overlaps': [
            {'first_clip_id': 'z', 'second_clip_id': 'a', 'start_frame': 10, 'end_frame': 15, 'duration_frames': 5},
            {'first_clip_id': 'z', 'second_clip_id': 'b', 'start_frame': 10, 'end_frame': 20, 'duration_frames': 10},
            {'first_clip_id': 'a', 'second_clip_id': 'b', 'start_frame': 10, 'end_frame': 15, 'duration_frames': 5},
        ], 'total_frames': 21,
    }


class PlanValidationTests(unittest.TestCase):
    def test_valid_and_all_pairs(self):
        validate_plan(example())

    def test_invalid_clip_invariants(self):
        for key, value in [('start_frame', -1), ('start_frame', 20),
                           ('end_frame', 9), ('duration_frames', 11),
                           ('duration_frames', True), ('id', 'a')]:
            p = example()
            p['clips'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ProjectError): validate_plan(p)
        for value in [20, True, -1, 21.0]:
            p = example(); p['total_frames'] = value
            with self.subTest(value=value), self.assertRaises(ProjectError): validate_plan(p)

    def test_invalid_overlap_invariants(self):
        for key, value in [('first_clip_id', 'missing'), ('second_clip_id', 'z'),
                           ('start_frame', 9), ('end_frame', 14),
                           ('duration_frames', 0), ('duration_frames', 5.0)]:
            p = example(); p['overlaps'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ProjectError): validate_plan(p)
        for mutation in ('missing', 'duplicate', 'reverse', 'order', 'extra'):
            p = example(); overlaps = p['overlaps']
            if mutation == 'missing': overlaps.pop()
            if mutation == 'duplicate': overlaps.append(copy.deepcopy(overlaps[0]))
            if mutation == 'reverse': overlaps[0]['first_clip_id'], overlaps[0]['second_clip_id'] = 'a', 'z'
            if mutation == 'order': overlaps.reverse()
            if mutation == 'extra': overlaps.append({'first_clip_id': 'b', 'second_clip_id': 'alone', 'start_frame': 20, 'end_frame': 20, 'duration_frames': 0})
            with self.subTest(mutation=mutation), self.assertRaises(ProjectError): validate_plan(p)

    def test_empty_and_unknown_fields(self):
        p = example(); p['clips'] = []; p['overlaps'] = []; p['total_frames'] = 0
        with self.assertRaises(ProjectError): validate_plan(p)
        p = example(); p['unexpected'] = 1
        with self.assertRaises(ProjectError): validate_plan(p)
        p = example(); p['plan_version'] = '0.2'
        with self.assertRaises(ProjectError): validate_plan(p)

    def test_json_and_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'plan.json'
            path.write_text(json.dumps(example()), encoding='utf-8')
            validate_plan(load_plan(path))
            result = subprocess.run([sys.executable, '-m', 'mashup', 'validate-plan', str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for text in ['{"x": 1, "x": 2}', '{"x": NaN}', '{oops']:
                path.write_text(text, encoding='utf-8')
                with self.subTest(text=text), self.assertRaises(ProjectError): load_plan(path)
            result = subprocess.run([sys.executable, '-m', 'mashup', 'validate-plan', str(path)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
