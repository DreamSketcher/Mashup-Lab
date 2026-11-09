import copy
import hashlib
import struct
import tempfile
import unittest
import wave
from pathlib import Path

import yaml
from mashup.model import ProjectError
from mashup.render import render


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source.wav'
        with wave.open(str(self.source), 'wb') as w:
            w.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
            w.writeframes(struct.pack('<4h', 16384, 16384, 16384, 16384))
        self.project = {'schema_version': '0.1',
            'timeline': {'bpm': 120, 'time_signature': [4, 4], 'ppq': 960, 'sample_rate': 48000},
            'sources': [{'id': 's', 'path': 'source.wav', 'sha256': hashlib.sha256(self.source.read_bytes()).hexdigest(), 'sample_rate': 48000, 'channels': 1, 'frames': 4}],
            'clips': [{'id': 'a', 'source_id': 's', 'source_range': {'start_frame': 0, 'end_frame': 4}, 'position': {'bar': 1, 'beat': 1, 'tick': 0},
                       'processing': {'duration_ratio': 1, 'pitch_semitones': 0, 'gain_db': 0, 'pan': 0, 'fade_in_frames': 0, 'fade_out_frames': 0}}],
            'render': {'bit_depth': 16}}
        self.path = self.root / 'project.yaml'

    def run_render(self, name='out.wav'):
        self.path.write_text(yaml.safe_dump(self.project))
        return render(self.path, self.root / name)

    def pcm(self, name='out.wav'):
        with wave.open(str(self.root / name), 'rb') as w:
            self.assertEqual((w.getnchannels(), w.getframerate()), (2, 48000))
            return w.readframes(w.getnframes())

    def test_repeat_and_geometry(self):
        second = copy.deepcopy(self.project['clips'][0])
        second['id'] = 'b'
        second['position']['tick'] = 1  # 25 frames
        self.project['clips'].append(second)
        a = self.run_render()
        b = self.run_render('again.wav')
        self.assertEqual(a, b)
        self.assertEqual(a['frames'], 29)
        pcm = self.pcm()
        self.assertEqual(a['pcm_sha256'], hashlib.sha256(pcm).hexdigest())
        frames = list(struct.iter_unpack('<hh', pcm))
        self.assertEqual(frames[:4], [(16384, 16384)] * 4)
        self.assertEqual(frames[4:25], [(0, 0)] * 21)
        self.assertEqual(frames[25:], [(16384, 16384)] * 4)
        self.assertEqual(pcm, self.pcm('again.wav'))

    def test_fades_pan_and_overlap_peak(self):
        p = self.project['clips'][0]['processing']
        p.update(pan=1, fade_in_frames=2, fade_out_frames=2)
        self.run_render()
        self.assertEqual(list(struct.iter_unpack('<hh', self.pcm())), [(0, 8192), (0, 16384), (0, 16384), (0, 8192)])
        p.update(pan=0, fade_in_frames=0, fade_out_frames=0, gain_db=6)
        self.project['clips'].append(copy.deepcopy(self.project['clips'][0]))
        self.project['clips'][1]['id'] = 'b'
        result = self.run_render('peak.wav')
        self.assertGreater(result['peak'], 1)
        self.assertAlmostEqual(result['scale'], 1 / result['peak'])
        self.assertEqual(list(struct.iter_unpack('<hh', self.pcm('peak.wav'))), [(32767, 32767)] * 4)

    def test_two_sources_overlap_and_stereo(self):
        source = self.root / 'stereo.wav'
        with wave.open(str(source), 'wb') as w:
            w.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
            w.writeframes(struct.pack('<8h', *([4096, -4096] * 4)))
        self.project['sources'].append({'id': 'stereo', 'path': 'stereo.wav',
            'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'sample_rate': 48000, 'channels': 2, 'frames': 4})
        second = copy.deepcopy(self.project['clips'][0])
        second.update(id='b', source_id='stereo')
        self.project['clips'].append(second)
        self.run_render()
        self.assertEqual(list(struct.iter_unpack('<hh', self.pcm())),
                         [(20480, 12288)] * 4)

    def test_24_bit_and_errors(self):
        self.project['render']['bit_depth'] = 24
        self.run_render()
        self.assertEqual(self.pcm(), b'\x00\x00\x40' * 8)
        for key, value in [('duration_ratio', 0.96), ('pitch_semitones', 1)]:
            self.project['clips'][0]['processing'][key] = value
            with self.assertRaisesRegex(ProjectError, 'not supported'): self.run_render('bad.wav')
            self.project['clips'][0]['processing'][key] = 1 if key == 'duration_ratio' else 0
        self.project['sources'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ProjectError, 'hash mismatch'): self.run_render('bad.wav')
        self.assertFalse((self.root / 'bad.wav').exists())

    def test_no_overwrite_and_rate_rejection(self):
        original = self.source.read_bytes()
        with self.assertRaisesRegex(ProjectError, 'cannot create output'): self.run_render('source.wav')
        self.assertEqual(self.source.read_bytes(), original)
        self.project['sources'][0]['sample_rate'] = 44100
        with self.assertRaisesRegex(ProjectError, 'resampling'): self.run_render('bad.wav')
