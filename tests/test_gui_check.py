import contextlib
import io
import subprocess
import unittest
from unittest.mock import patch

from mashup import gui_check


class GuiEnvironmentCheckTests(unittest.TestCase):
    def test_missing_ffmpeg_is_reported(self):
        with patch('mashup.conversion.ffmpeg_executable', side_effect=RuntimeError('missing binary')):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = gui_check.main()
        self.assertEqual(result, 1)
        self.assertIn('FFmpeg: недоступен: missing binary', output.getvalue())
        self.assertIn('пункт 8', output.getvalue())

    def test_nonworking_executable_is_reported(self):
        with patch('mashup.conversion.ffmpeg_executable', return_value='ffmpeg'), \
             patch('subprocess.run', side_effect=subprocess.TimeoutExpired('ffmpeg', 15)):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = gui_check.main()
        self.assertEqual(result, 1)
        self.assertIn('FFmpeg: недоступен', output.getvalue())


if __name__ == '__main__':
    unittest.main()
