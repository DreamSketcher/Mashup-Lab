import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

from mashup.model import load_project, plan_project


class QuickMashupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.a = self.root / 'голос 1.wav'
        self.b = self.root / 'audio 2.wav'
        self.write_wave(self.a, 1, 48000, [8192] * 4)
        self.write_wave(self.b, 2, 48000, [4096, -4096] * 4)

    def write_wave(self, path, channels, rate, values):
        with wave.open(str(path), 'wb') as w:
            w.setparams((channels, 2, rate, 0, 'NONE', 'not compressed'))
            w.writeframes(struct.pack('<' + 'h' * len(values), *values))

    def call(self, *args):
        return subprocess.run([sys.executable, '-m', 'mashup', 'quick-mashup', *map(str, args)],
                              text=True, encoding='utf-8', capture_output=True)

    def test_end_to_end_and_repeat(self):
        folder = self.root / 'мой проект'
        result = self.call(self.a, self.b, '--project-dir', folder, '--bit-depth', 16,
                           '--tick2', 1, '--verify-repeat')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['repeat_pcm_match'])
        self.assertEqual(report['render']['frames'], 29)
        self.assertEqual(report['plan']['clips'][1]['start_frame'], 25)
        project = load_project(folder / 'project.yaml')
        self.assertEqual(plan_project(project, folder).total_frames, 29)
        self.assertEqual((folder / 'sources' / 'audio1.wav').read_bytes(), self.a.read_bytes())
        with wave.open(str(folder / 'mashup.wav'), 'rb') as w:
            self.assertEqual((w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()), (48000, 2, 2, 29))
            pcm = w.readframes(w.getnframes())
        self.assertEqual(hashlib.sha256(pcm).hexdigest(), report['render']['pcm_sha256'])
        samples = list(struct.iter_unpack('<hh', pcm))
        self.assertEqual(samples[:4], [(8192, 8192)] * 4)
        self.assertEqual(samples[4:25], [(0, 0)] * 21)
        self.assertEqual(samples[25:], [(4096, -4096)] * 4)

    def test_default_overlay_and_peak_protection(self):
        folder = self.root / 'mix'
        result = self.call(self.a, self.a, '--project-dir', folder, '--gain1', 12, '--gain2', 12)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['render']['frames'], 4)
        self.assertGreater(report['render']['peak'], 1)
        self.assertLess(report['render']['scale'], 1)
        self.assertIsNone(report['repeat_pcm_match'])
        self.assertEqual(report['plan']['overlaps'][0]['end_frame'], 4)

    def test_edit_options(self):
        folder = self.root / 'edit'
        result = self.call(self.a, self.b, '--project-dir', folder, '--start1', 1, '--end1', 3,
                           '--fade-in1', 2, '--fade-out1', 1, '--gain2', '-6.5',
                           '--pan2', '-0.25', '--bpm', '123.5', '--beat2', 2)
        self.assertEqual(result.returncode, 0, result.stderr)
        p = load_project(folder / 'project.yaml')
        self.assertEqual(str(p['timeline']['bpm']), '123.5')
        self.assertEqual(str(p['clips'][1]['processing']['gain_db']), '-6.5')
        self.assertEqual(p['clips'][0]['source_range'], {'start_frame': 1, 'end_frame': 3})
        self.assertEqual(p['clips'][0]['processing']['fade_in_frames'], 2)
        self.assertGreater(json.loads(result.stdout)['plan']['clips'][1]['start_frame'], 0)

    def test_preflight_rejects_and_never_overwrites(self):
        bad = self.root / 'bad.wav'
        self.write_wave(bad, 1, 44100, [1, 2])
        for options, message in [([bad, self.b], '48000 Hz'),
                                  ([self.a, self.b, '--end1', '9'], 'end_frame'),
                                  ([self.a, self.b, '--beat2', '5'], 'beat'),
                                  ([self.a, self.b, '--fade-in1', '5'], 'fade_in_frames'),
                                  ([self.a, self.b, '--pan2', '2'], 'pan')]:
            folder = self.root / 'not-created'
            result = self.call(*options, '--project-dir', folder)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(message, result.stderr)
            self.assertFalse(folder.exists())
        folder = self.root / 'existing'
        folder.mkdir()
        marker = folder / 'project.yaml'
        marker.write_text('keep')
        result = self.call(self.a, self.b, '--project-dir', folder)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(marker.read_text(), 'keep')
        self.assertEqual(self.a.stat().st_size, 52)

    def test_truncated_source_fails_without_success_report(self):
        bad = self.root / 'truncated.wav'
        bad.write_bytes(self.a.read_bytes()[:-2])
        folder = self.root / 'partial'
        result = self.call(bad, self.b, '--project-dir', folder)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('truncated WAV', result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertTrue(folder.exists())
        self.assertFalse((folder / 'mashup.wav').exists())

    def test_help_and_invalid_decimal(self):
        help_result = self.call('--help')
        self.assertEqual(help_result.returncode, 0)
        self.assertIn('--project-dir', help_result.stdout)
        result = self.call(self.a, self.b, '--project-dir', self.root / 'p', '--bpm', 'nan')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'p').exists())


if __name__ == '__main__':
    unittest.main()
