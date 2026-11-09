import contextlib
import io
import tempfile
import unittest
from pathlib import Path

try:
    import numpy as np
    import soundfile as sf
    import librosa
    import music_key_detector
except ImportError:
    np = None

from mashup.audio_analysis import analyze


@unittest.skipIf(np is None, 'audio analysis dependencies not installed')
class AnalysisTests(unittest.TestCase):
    def test_empty_silence_and_short(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'silence.wav'
            sf.write(file, np.zeros(22050 * 4), 22050)
            result = analyze(file)
            self.assertIsNone(result['bpm']); self.assertIsNone(result['key'])
            sf.write(file, np.ones(22050), 22050)
            self.assertIsNone(analyze(file)['key'])
            with self.assertRaises(ValueError): analyze(Path(tmp) / 'absent.wav')

    def test_real_c_major_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'accord.wav'
            rate = 22050
            time = np.arange(rate * 6) / rate
            y = sum(.1 * np.sin(2*np.pi*frequency*time) for frequency in (261.6256,329.6276,391.9954))
            sf.write(file, y, rate)
            result = analyze(file)
            self.assertEqual((result['key']['name'], result['key']['mode']), ('C', 'major'))
            self.assertEqual(result['duration_seconds'], 6)
