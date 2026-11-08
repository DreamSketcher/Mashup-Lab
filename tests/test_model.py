import copy
import hashlib
import tempfile
import unittest
import wave
from pathlib import Path
from fractions import Fraction

from mashup.model import ProjectError, load_project, plan_project, round_half_up


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.audio = self.root / 'audio.wav'
        with wave.open(str(self.audio), 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(48000)
            w.writeframes(b'\0\0' * 48000)
        h = hashlib.sha256(self.audio.read_bytes()).hexdigest()
        self.project = {
            'schema_version': '0.1',
            'timeline': {'bpm': 125, 'time_signature': [4, 4], 'ppq': 960, 'sample_rate': 48000},
            'sources': [{'id': 'src', 'path': 'audio.wav', 'sha256': h, 'sample_rate': 48000, 'channels': 1, 'frames': 48000}],
            'clips': [{'id': 'one', 'source_id': 'src', 'source_range': {'start_frame': 0, 'end_frame': 48000},
                       'position': {'bar': 1, 'beat': 1, 'tick': 0},
                       'processing': {'duration_ratio': 1, 'pitch_semitones': 0, 'gain_db': 0, 'pan': 0, 'fade_in_frames': 0, 'fade_out_frames': 0}}],
            'render': {'bit_depth': 24},
        }

    def plan(self):
        return plan_project(self.project, self.root)

    def test_positions_overlaps_and_end(self):
        other = copy.deepcopy(self.project['clips'][0])
        other['id'] = 'two'
        other['position'] = {'bar': 1, 'beat': 2, 'tick': 0}
        self.project['clips'].append(other)
        plan = self.plan()
        self.assertEqual((plan.clips[1].start, plan.clips[1].end), (23040, 71040))
        self.assertEqual(plan.overlaps, (('one', 'two', 23040, 48000),))
        self.assertEqual(plan.total_frames, 71040)
        other['position'] = {'bar': 2, 'beat': 1, 'tick': 0}
        self.assertEqual(self.plan().clips[1].start, 92160)
        self.assertEqual(self.plan().overlaps, ())

    def test_exact_half_and_duration(self):
        self.assertEqual(round_half_up(Fraction(1, 2)), 1)
        self.assertEqual(round_half_up(Fraction(149, 100)), 1)
        self.project['clips'][0]['processing']['duration_ratio'] = __import__('decimal').Decimal('0.96')
        self.assertEqual(self.plan().total_frames, 46080)
        # 1 tick at 120 BPM = 25 frames; at 240 BPM = 12.5 frames.
        self.project['timeline']['bpm'] = 240
        self.project['clips'][0]['position']['tick'] = 1
        self.assertEqual(self.plan().clips[0].start, 13)

    def test_denominator_note(self):
        self.project['timeline']['time_signature'] = [6, 8]
        self.project['clips'][0]['position'] = {'bar': 2, 'beat': 1, 'tick': 0}
        self.assertEqual(self.plan().clips[0].start, 69120)
        self.project['clips'][0]['position']['tick'] = 480
        with self.assertRaises(ProjectError): self.plan()

    def test_adjacent_clips_do_not_overlap(self):
        other = copy.deepcopy(self.project['clips'][0])
        other['id'] = 'two'
        self.project['timeline']['bpm'] = 120
        other['position']['beat'] = 3
        self.project['clips'].append(other)
        self.assertEqual(self.plan().overlaps, ())
        self.assertEqual(self.plan().total_frames, 96000)

    def test_bad_sources_and_fades(self):
        self.project['sources'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ProjectError, 'hash mismatch'): self.plan()
        self.project['sources'][0]['sha256'] = hashlib.sha256(self.audio.read_bytes()).hexdigest()
        self.project['clips'][0]['processing']['fade_in_frames'] = 48001
        with self.assertRaises(ProjectError): self.plan()
        self.project['clips'][0]['processing']['fade_in_frames'] = 0
        self.project['sources'][0]['path'] = '../escape.wav'
        with self.assertRaises(ProjectError): self.plan()

    def test_duplicate_ids_and_fields(self):
        self.project['clips'].append(copy.deepcopy(self.project['clips'][0]))
        with self.assertRaisesRegex(ProjectError, 'duplicate clip'): self.plan()
        self.project['clips'].pop()
        self.project['clips'][0]['extra'] = 1
        with self.assertRaises(ProjectError): self.plan()

    def test_yaml_decimal_duplicate_alias_tag(self):
        p = self.root / 'test.yaml'
        p.write_text('value: 0.96000000000000000001\n')
        self.assertEqual(str(load_project(p)['value']), '0.96000000000000000001')
        for text in ('a: 1\na: 2\n', 'a: &x 1\nb: *x\n', 'a: !!str hello\n', 'a: 012\n'):
            p.write_text(text)
            with self.subTest(text=text), self.assertRaises(ProjectError): load_project(p)

    def test_missing_wrong_metadata_and_zero_length(self):
        self.project['sources'][0]['frames'] = 47999
        with self.assertRaisesRegex(ProjectError, 'metadata mismatch'): self.plan()
        self.project['sources'][0]['frames'] = 48000
        self.audio.unlink()
        with self.assertRaises(ProjectError): self.plan()
        self.project['sources'][0]['sample_rate'] = 192000
        self.project['clips'][0]['source_range']['end_frame'] = 1
        self.project['clips'][0]['processing']['duration_ratio'] = __import__('decimal').Decimal('0.5')
        with self.assertRaisesRegex(ProjectError, 'zero frames'):
            plan_project(self.project, self.root, verify_sources=False)

    def test_fractional_bpm_and_tick_rounding(self):
        from decimal import Decimal
        self.project['timeline']['bpm'] = Decimal('119.88')
        self.project['clips'][0]['position']['tick'] = 100
        # 100 * 60 * 48000 / (960 * 119.88) = 2502.5025...
        self.assertEqual(self.plan().clips[0].start, 2503)
        self.project['timeline']['bpm'] = 240
        for tick, expected in [(1, 13), (2, 25), (3, 38)]:
            self.project['clips'][0]['position']['tick'] = tick
            self.assertEqual(self.plan().clips[0].start, expected)

    def test_short_clips_and_ratio_boundaries(self):
        from decimal import Decimal
        clip = self.project['clips'][0]
        clip['source_range']['end_frame'] = 1
        for ratio, expected in [('0.5', 1), ('2', 2)]:
            clip['processing']['duration_ratio'] = Decimal(ratio)
            self.assertEqual(self.plan().total_frames, expected)
        for ratio in ['0.499', '2.001']:
            clip['processing']['duration_ratio'] = Decimal(ratio)
            with self.subTest(ratio=ratio), self.assertRaises(ProjectError): self.plan()

    def test_contained_and_identical_overlaps(self):
        self.project['timeline']['bpm'] = 120
        small = copy.deepcopy(self.project['clips'][0])
        small['id'] = 'small'
        small['source_range']['end_frame'] = 1000
        small['position']['tick'] = 1  # 25 frames
        duplicate = copy.deepcopy(self.project['clips'][0])
        duplicate['id'] = 'duplicate'
        self.project['clips'] += [small, duplicate]
        self.assertEqual(self.plan().overlaps, (
            ('one', 'small', 25, 1025), ('one', 'duplicate', 0, 48000),
            ('small', 'duplicate', 25, 1025)))

    def test_wav_header_format_and_metadata(self):
        def replace_audio(data):
            self.audio.write_bytes(data)
            self.project['sources'][0]['sha256'] = hashlib.sha256(data).hexdigest()
        valid = self.audio.read_bytes()
        replace_audio(b'not a WAV')
        with self.assertRaises(ProjectError): self.plan()
        replace_audio(valid[:-1])
        with self.assertRaisesRegex(ProjectError, 'truncated WAV'): self.plan()
        replace_audio(valid)
        for key, value in [('frames', 47999), ('channels', 2), ('sample_rate', 44100)]:
            original = self.project['sources'][0][key]
            self.project['sources'][0][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ProjectError, 'metadata mismatch'): self.plan()
            self.project['sources'][0][key] = original
        # A syntactically valid 8-bit PCM WAV is outside the supported subset.
        with wave.open(str(self.audio), 'wb') as w:
            w.setnchannels(1); w.setsampwidth(1); w.setframerate(48000); w.writeframes(b'\x80' * 48000)
        self.project['sources'][0]['sha256'] = hashlib.sha256(self.audio.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ProjectError, 'unsupported WAV'): self.plan()

    def test_yaml_invalid_numbers_and_types(self):
        p = self.root / 'test.yaml'
        for token in ['.nan', '.inf', '-.inf']:
            p.write_text(f'bpm: {token}\n')
            with self.subTest(token=token), self.assertRaises(ProjectError): load_project(p)
        for value in [True, '120', None, 0, -1]:
            self.project['timeline']['bpm'] = value
            with self.subTest(value=value), self.assertRaises(ProjectError): self.plan()

    def test_cli_plan_json_and_errors(self):
        import json
        import subprocess
        import sys
        import yaml
        path = self.root / 'project.yaml'
        path.write_text(yaml.safe_dump(self.project), encoding='utf-8')
        command = [sys.executable, '-m', 'mashup', 'plan', str(path)]
        first = subprocess.run(command, text=True, capture_output=True)
        second = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(json.loads(first.stdout), self.plan().to_dict())
        from mashup.plan_validation import validate_plan
        validate_plan(json.loads(first.stdout))
        self.audio.unlink()
        failed = subprocess.run(command, text=True, capture_output=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(failed.stdout, '')
        self.assertIn('error:', failed.stderr)

    def test_plan_artifact(self):
        expected = {'plan_version': '0.1', 'sample_rate': 48000,
                    'clips': [{'id': 'one', 'start_frame': 0, 'end_frame': 48000, 'duration_frames': 48000}],
                    'overlaps': [], 'total_frames': 48000}
        self.assertEqual(self.plan().to_dict(), expected)
        self.assertEqual(self.plan().to_dict(), self.plan().to_dict())

    def test_reference_coordinates_and_duration(self):
        from decimal import Decimal
        # Hand-calculated vectors: 48 kHz / 120 BPM gives 24,000 frames
        # per quarter and 25 frames per PPQ tick. 6/8 beats are eighths.
        cases = [
            (120, [4, 4], (1, 1, 0), 0),
            (120, [4, 4], (3, 2, 4), 216100),
            (120, [6, 8], (2, 3, 0), 96000),
            (240, [4, 4], (1, 1, 1), 13),  # exactly 12.5
            (Decimal('119.88'), [4, 4], (1, 1, 100), 2503),
        ]
        clip = self.project['clips'][0]
        for bpm, signature, (bar, beat, tick), expected in cases:
            self.project['timeline']['bpm'] = bpm
            self.project['timeline']['time_signature'] = signature
            clip['position'] = {'bar': bar, 'beat': beat, 'tick': tick}
            with self.subTest(bpm=bpm, position=clip['position']):
                self.assertEqual(self.plan().clips[0].start, expected)
        # 1001 input frames at 32 kHz represent 1501.5 output frames;
        # ratio 1 rounds the final length to 1502, without intermediate rounding.
        self.project['sources'][0]['sample_rate'] = 32000
        clip['source_range']['end_frame'] = 1001
        result = plan_project(self.project, self.root, verify_sources=False)
        self.assertEqual(result.clips[0].end - result.clips[0].start, 1502)

    def test_reordering_changes_pair_order_not_geometry(self):
        base = self.project['clips'][0]
        base['id'] = 'z'
        b = copy.deepcopy(base); b['id'] = 'a'; b['position']['tick'] = 480
        c = copy.deepcopy(base); c['id'] = 'm'; c['position']['beat'] = 2
        self.project['timeline']['bpm'] = 120
        self.project['clips'] = [base, b, c]
        self.assertEqual(self.plan().overlaps, (
            ('z', 'a', 12000, 48000), ('z', 'm', 24000, 48000),
            ('a', 'm', 24000, 60000)))
        self.project['clips'] = [c, base, b]
        self.assertEqual(self.plan().overlaps, (
            ('m', 'z', 24000, 48000), ('m', 'a', 24000, 60000),
            ('z', 'a', 12000, 48000)))

    def test_large_values_and_many_clips(self):
        # Timing-model stress only: metadata is intentionally synthetic, so this
        # test does not claim that these samples exist or that WAV was validated.
        self.project['timeline']['bpm'] = 1000000000
        self.project['clips'][0]['position']['tick'] = 1
        self.assertEqual(self.plan().clips[0].start, 0)
        self.project['timeline']['bpm'] = 120
        clip = self.project['clips'][0]
        clip['position'] = {'bar': 1000000000001, 'beat': 1, 'tick': 0}
        self.project['sources'][0]['frames'] = 1000000000000
        clip['source_range']['end_frame'] = 1000000000000
        clip['processing']['duration_ratio'] = 2
        plan = plan_project(self.project, self.root, verify_sources=False)
        self.assertEqual(plan.clips[0].start, 96000000000000000)
        self.assertEqual(plan.total_frames, 96002000000000000)
        # 200 simultaneous clips produce exactly n(n-1)/2 pairwise overlaps.
        clip['position'] = {'bar': 1, 'beat': 1, 'tick': 0}
        clip['source_range']['end_frame'] = 1
        self.project['clips'] = []
        for i in range(200):
            item = copy.deepcopy(clip); item['id'] = f'clip_{i}'
            self.project['clips'].append(item)
        plan = plan_project(self.project, self.root, verify_sources=False)
        self.assertEqual(len(plan.clips), 200)
        self.assertEqual(len(plan.overlaps), 19900)
        self.assertEqual(plan.overlaps[0], ('clip_0', 'clip_1', 0, 2))
        self.assertEqual(plan.overlaps[-1], ('clip_198', 'clip_199', 0, 2))
        from mashup.plan_validation import validate_plan
        validate_plan(plan.to_dict())

    def test_repeated_json_across_process_hash_seeds(self):
        import json
        import os
        import subprocess
        import sys
        import yaml
        path = self.root / 'project.yaml'
        other = copy.deepcopy(self.project['clips'][0])
        other['id'] = 'two'; other['position']['beat'] = 2
        self.project['clips'].append(other)
        path.write_text(yaml.safe_dump(self.project), encoding='utf-8')
        command = [sys.executable, '-m', 'mashup', 'plan', str(path)]
        outputs = []
        for seed in ('0', '1', '12345'):
            env = {**os.environ, 'PYTHONHASHSEED': seed}
            result = subprocess.run(command, capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.append(result.stdout)
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[1], outputs[2])
        self.assertEqual(json.loads(outputs[0]), {
            'plan_version': '0.1', 'sample_rate': 48000,
            'clips': [
                {'id': 'one', 'start_frame': 0, 'end_frame': 48000, 'duration_frames': 48000},
                {'id': 'two', 'start_frame': 23040, 'end_frame': 71040, 'duration_frames': 48000},
            ],
            'overlaps': [{'first_clip_id': 'one', 'second_clip_id': 'two',
                          'start_frame': 23040, 'end_frame': 48000, 'duration_frames': 24960}],
            'total_frames': 71040,
        })


if __name__ == "__main__":
    unittest.main()
