import hashlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import wave

from mashup import separation


class FakeSeparator:
    def __init__(self, **kwargs): self.output = Path(kwargs['output_dir'])
    def load_model(self, name): self.name = name
    def separate(self, path, custom_output_names):
        for name in custom_output_names.values():
            with wave.open(str(self.output / (name + '.wav')), 'wb') as w:
                w.setparams((2,2,44100,0,'NONE','not compressed')); w.writeframes(b'\x00\x10\x00\x10' * 4410)


class SeparationTests(unittest.TestCase):
    def test_pipeline_produces_wavs_without_overwriting_source(self):
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            self.skipTest('optional ffmpeg not installed')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'source.wav'
            with wave.open(str(source), 'wb') as w:
                w.setparams((1,2,48000,0,'NONE','not compressed')); w.writeframes(b'\x00\x10' * 4800)
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            modules = {'audio_separator': types.ModuleType('audio_separator'),
                       'audio_separator.separator': types.SimpleNamespace(Separator=FakeSeparator)}
            with patch.object(separation.model_store, 'check', return_value=True), patch.dict(sys.modules, modules), patch.dict('os.environ', {}, clear=False):
                result = separation.separate(source, root / 'out', exe, model_dir=root)
                for path in result['outputs'].values():
                    with wave.open(path, 'rb') as w:
                        self.assertEqual((w.getframerate(), w.getnchannels(), w.getsampwidth()), (48000,2,2))
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
                with self.assertRaises(FileExistsError): separation.separate(source, root / 'out', exe, model_dir=root)

    def test_missing_model_stops_before_creating_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(separation.model_store, 'check', return_value=False):
                with self.assertRaises(ValueError): separation.separate('missing', Path(tmp)/'out', 'missing')
            self.assertFalse((Path(tmp)/'out').exists())
