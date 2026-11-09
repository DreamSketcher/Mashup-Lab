"""Optional PySide6 GUI smoke tests (headless Qt offscreen)."""
import json
import os
from pathlib import Path
import struct
import tempfile
import time
import unittest
import wave

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtWidgets import QApplication
    from mashup.gui import MashupWindow
except ImportError as exc:
    GUI_IMPORT_ERROR = str(exc)
else:
    GUI_IMPORT_ERROR = None

from mashup.session_trace import SessionTrace


class TraceTests(unittest.TestCase):
    def test_persistent_unicode_events_and_write_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = SessionTrace(tmp)
            trace.emit('application.start', path='путь')
            trace.emit('ui.click', control='render')
            rows = [json.loads(x) for x in trace.path.read_text(encoding='utf-8').splitlines()]
            self.assertEqual([x['event'] for x in rows], ['application.start','ui.click'])
            self.assertEqual(rows[0]['path'], 'путь')
            self.assertTrue(rows[0]['time_utc'].endswith('+00:00'))
            blocked = Path(tmp) / 'not-a-directory'; blocked.write_text('test')
            broken = SessionTrace(blocked)
            self.assertIsNone(broken.path)
            self.assertTrue(broken.error)
            self.assertEqual(broken.emit('still.responds')['event'], 'still.responds')


@unittest.skipIf(GUI_IMPORT_ERROR, f'optional Qt runtime unavailable: {GUI_IMPORT_ERROR}')
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.trace = SessionTrace(self.root / 'traces')
        self.window = MashupWindow(self.trace)
        self.addCleanup(self.window.close)
        self.window.show(); self.app.processEvents()
        for i in (1,2):
            path = self.root / f'звук {i}.wav'
            with wave.open(str(path), 'wb') as wav:
                wav.setparams((1,2,48000,0,'NONE','not compressed'))
                wav.writeframes(struct.pack('<4h', 4096, 4096, 4096, 4096))
            self.window.tracks[i-1]['path'].setText(str(path))
            self.window.read_header(i)
        self.window.output_dir.setText(str(self.root / 'новый проект'))

    def wait_render(self):
        deadline = time.monotonic() + 30
        while self.window.process is not None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertIsNone(self.window.process, 'render process timed out')

    def trace_rows(self):
        return [json.loads(line) for line in self.trace.path.read_text(encoding='utf-8').splitlines()]

    def test_two_files_render_and_trace(self):
        self.window.tracks[1]['tick'].setValue(1)
        self.window.run(); self.wait_render()
        self.assertTrue(self.window.open_output.isEnabled(), self.window.run_status.text())
        with wave.open(str(self.root / 'новый проект' / 'mashup.wav'), 'rb') as wav:
            self.assertEqual((wav.getnchannels(), wav.getframerate(), wav.getnframes()), (2,48000,29))
        events = [row['event'] for row in self.trace_rows()]
        for event in ('ui.ready','ui.source_loaded','ui.value_changed','ui.render_clicked',
                      'backend.start','backend.quick.project_validated', 'backend.render.clip_mixed',
                      'backend.quick.repeat_complete','backend.success','backend.finished'):
            self.assertIn(event, events)
        row = next(row for row in self.trace_rows() if row['event'] == 'backend.success')
        self.assertTrue(row['report']['repeat_pcm_match'])

    def test_bad_format_reports_error_and_does_not_make_project(self):
        path = self.root / '44100.wav'
        with wave.open(str(path), 'wb') as wav:
            wav.setparams((1,2,44100,0,'NONE','not compressed')); wav.writeframes(b'\x00\x00'*8)
        self.window.tracks[0]['path'].setText(str(path)); self.window.read_header(1)
        self.window.run(); self.wait_render()
        self.assertFalse(self.window.open_output.isEnabled())
        self.assertFalse((self.root / 'новый проект').exists())
        rows = self.trace_rows()
        self.assertTrue(any(x['event'] == 'backend.quick.error' and '48000' in x['error'] for x in rows))
        self.assertTrue(any(x['event'] == 'backend.failed' for x in rows))


if __name__ == '__main__':
    unittest.main()
