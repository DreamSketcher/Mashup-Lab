"""Optional PySide6 GUI smoke tests (headless Qt offscreen)."""
import hashlib
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
        self.window = MashupWindow(self.trace, self.root / 'конвертировано')
        self.addCleanup(self.window.close)
        self.window.show(); self.window.switch_page(0); self.app.processEvents()
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

    def wait_conversion(self):
        deadline = time.monotonic() + 30
        while self.window.converter_process is not None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertIsNone(self.window.converter_process, 'conversion process timed out')

    def test_navigation_and_nonmodal_file_picker(self):
        for index in range(5):
            self.window.nav.button(index).click()
            self.assertEqual(self.window.stack.currentIndex(), index)
        self.window.choose_file(1)
        self.app.processEvents()
        self.assertTrue(self.window._dialogs)
        dialog = self.window._dialogs[-1]
        self.assertFalse(dialog.isModal())
        dialog.reject(); self.app.processEvents()
        self.assertTrue(any(row['event'] == 'ui.page_changed' for row in self.trace_rows()))

    def test_conversion_and_use_as_source(self):
        try:
            from mashup.conversion import ffmpeg_executable
            ffmpeg_executable()
        except Exception:
            self.skipTest('optional FFmpeg not installed')
        source = self.root / 'аудио 44.1.wav'
        with wave.open(str(source), 'wb') as wav:
            wav.setparams((1,2,44100,0,'NONE','not compressed'))
            wav.writeframes(struct.pack('<4410h', *([2048]*4410)))
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        self.window.tracks[0]['path'].setText(str(source)); self.window.read_header(1)
        self.window.send_to_conversion(1)
        self.assertEqual(self.window.stack.currentIndex(), 1)
        self.window.convert(); self.wait_conversion()
        destination = Path(self.window.conversion_output.text())
        self.assertEqual(destination.parent, self.root / 'конвертировано')
        self.assertTrue(destination.is_file(), self.window.conversion_status.text())
        self.assertTrue(self.window.use_converted1.isEnabled())
        with wave.open(str(destination), 'rb') as wav:
            self.assertEqual((wav.getnchannels(), wav.getframerate(), wav.getsampwidth(), wav.getnframes()), (2,48000,2,4800))
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
        self.window.to_processing.click()
        self.assertEqual(self.window.stack.currentIndex(), 4)
        self.assertEqual(self.window.processing_input.text(), str(destination))
        self.window.use_processing_input(1)
        self.assertEqual(self.window.stack.currentIndex(), 0)
        self.assertEqual(self.window.tracks[0]['path'].text(), str(destination))
        self.window.run(); self.wait_render()
        self.assertTrue(self.window.open_output.isEnabled(), self.window.run_status.text())
        with wave.open(str(self.root / 'новый проект' / 'mashup.wav'), 'rb') as wav:
            self.assertEqual(wav.getnframes(), 4800)
        events = [row['event'] for row in self.trace_rows()]
        for name in ('conversion.requested','conversion.started','conversion.ffmpeg',
                     'conversion.progress','conversion.completed','conversion.finished',
                     'processing.input_from_conversion','processing.use_input','backend.success'):
            self.assertIn(name, events)

    def test_processing_output_selection(self):
        vocals = self.root / 'vocals.wav'; instrumental = self.root / 'instrumental.wav'
        for path in (vocals, instrumental):
            with wave.open(str(path), 'wb') as w:
                w.setparams((1,2,48000,0,'NONE','not compressed')); w.writeframes(b'\0\0' * 4)
        self.window.engine_result = {'vocals': str(vocals), 'instrumental': str(instrumental)}
        self.window.stem_choice.setCurrentIndex(0); self.window.use_stem(1)
        self.assertEqual(self.window.tracks[0]['path'].text(), str(vocals))
        self.window.stem_choice.setCurrentIndex(1); self.window.use_stem(2)
        self.assertEqual(self.window.tracks[1]['path'].text(), str(instrumental))
        self.assertEqual(self.window.stack.currentIndex(), 0)
        self.assertTrue(any(row['event'] == 'processing.use_output' for row in self.trace_rows()))

    def test_create_button_visible_at_minimum_size(self):
        self.window.resize(900, 700); self.app.processEvents()
        self.assertTrue(self.window.make.isVisible())
        rect = self.window.make.rect()
        pos = self.window.make.mapTo(self.window, rect.topLeft())
        self.assertGreaterEqual(pos.x(), 0)
        self.assertGreaterEqual(pos.y(), 0)
        self.assertLessEqual(pos.x() + rect.width(), self.window.width())
        self.assertLessEqual(pos.y() + rect.height(), self.window.height())
        self.window.make.click(); self.wait_render()
        self.assertTrue(self.window.open_output.isEnabled(), self.window.run_status.text())

    def test_conversion_unique_names(self):
        from mashup.conversion import ffmpeg_executable
        try:
            ffmpeg_executable()
        except Exception:
            self.skipTest('optional FFmpeg not installed')
        self.window.conversion_input.setText(str(self.root / 'звук 1.wav'))
        self.window.convert(); self.wait_conversion()
        first = Path(self.window.conversion_output.text()); before = first.read_bytes()
        self.window.convert(); self.wait_conversion()
        second = Path(self.window.conversion_output.text())
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), before)
        self.assertTrue(second.exists())

    def test_conversion_invalid_audio_and_cancel(self):
        from mashup.conversion import ffmpeg_executable
        try:
            ffmpeg_executable()
        except Exception:
            self.skipTest('optional FFmpeg not installed')
        invalid = self.root / 'not-audio.wav'; invalid.write_bytes(b'not audio')
        self.window.conversion_input.setText(str(invalid))
        self.window.convert(); self.wait_conversion()
        self.assertFalse(Path(self.window.conversion_output.text()).exists())
        self.assertIn('conversion.failed', [row['event'] for row in self.trace_rows()])
        self.window.conversion_input.setText(str(self.root / 'звук 1.wav'))
        self.window.convert()
        self.window.cancel_conversion(); self.wait_conversion()
        self.assertFalse(Path(self.window.conversion_output.text()).exists())
        self.assertIn('conversion.cancelled', [row['event'] for row in self.trace_rows()])

    def test_analysis_runs_without_modifying_project(self):
        import math
        path = self.root / 'тональность.wav'
        rate = 22050
        with wave.open(str(path), 'wb') as wav:
            wav.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
            samples = (int(4000 * sum(math.sin(2 * math.pi * f * i / rate) for f in (261.6256, 329.6276, 391.9954))) for i in range(rate * 6))
            wav.writeframes(struct.pack('<' + str(rate * 6) + 'h', *samples))
        self.window.set_processing_input(str(path))
        self.window.switch_page(4)
        self.window.analyze_processing()
        deadline = time.monotonic() + 120
        while self.window.analysis_process is not None and time.monotonic() < deadline:
            self.app.processEvents(); time.sleep(.02)
        self.assertIsNone(self.window.analysis_process)
        self.assertIn('Тональность: C major', self.window.analysis_info.text())
        self.assertEqual(self.window.bpm.value(), 120)
        self.assertTrue(any(x['event'] == 'analysis.completed' for x in self.trace_rows()))

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
