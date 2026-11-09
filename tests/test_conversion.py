import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import wave

from mashup.conversion import prepare, publish, ffmpeg_executable
from mashup.model import ProjectError


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'оригинал 44.wav'
        with wave.open(str(self.source), 'wb') as wav:
            wav.setparams((1, 2, 44100, 0, 'NONE', 'not compressed'))
            wav.writeframes(struct.pack('<4410h', *([1000] * 4410)))

    def test_validates_paths_without_touching_original(self):
        original = self.source.read_bytes()
        for destination in (self.source, self.root / 'bad.mp3', self.root / 'missing' / 'new.wav'):
            with self.assertRaises(ProjectError): prepare(self.source, destination, 2)
        self.assertEqual(original, self.source.read_bytes())
        with self.assertRaises(ProjectError): prepare(self.source, self.root / 'new.wav', 6)

    def test_no_overwrite_at_publish(self):
        workspace, stage, _ = prepare(self.source, self.root / 'out.wav', 2)
        self.addCleanup(workspace.cleanup)
        with wave.open(str(stage), 'wb') as wav:
            wav.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\0' * 16)
        destination = self.root / 'out.wav'
        destination.write_bytes(b'keep')
        with self.assertRaises(ProjectError): publish(stage, destination, 2)
        self.assertEqual(destination.read_bytes(), b'keep')

    def test_reject_invalid_and_truncated_output(self):
        dest = self.root / 'result.wav'
        workspace, stage, _ = prepare(self.source, dest, 1)
        self.addCleanup(workspace.cleanup)
        stage.write_bytes(b'broken')
        with self.assertRaises(ProjectError): publish(stage, dest, 1)
        self.assertFalse(dest.exists())
        with wave.open(str(stage), 'wb') as wav:
            wav.setparams((1, 2, 48000, 0, 'NONE', 'not compressed')); wav.writeframes(b'\0'*20)
        stage.write_bytes(stage.read_bytes()[:-2])
        with self.assertRaises(ProjectError): publish(stage, dest, 1)
        self.assertFalse(dest.exists())

    def test_real_ffmpeg_when_installed(self):
        try:
            exe = ffmpeg_executable()
        except ProjectError:
            self.skipTest('optional FFmpeg package not installed')
        for channels in (1,2):
            dest = self.root / f'готово {channels}.wav'
            workspace, stage, args = prepare(self.source, dest, channels)
            try:
                result = subprocess.run([exe, *args], capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8','replace'))
                info = publish(stage, dest, channels)
                self.assertEqual((info['sample_rate'], info['channels'], info['bits'], info['frames']), (48000, channels, 16, 4800))
                self.assertTrue(dest.exists())
            finally:
                workspace.cleanup()
        self.assertTrue(self.source.exists())


if __name__ == '__main__':
    unittest.main()
