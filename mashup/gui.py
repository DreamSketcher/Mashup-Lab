"""Small PySide6 frontend for the existing two-source CLI.

Logs application actions and instrumented backend stages, not every OS/Qt/DSP
operation. Audio is never included in the trace.
"""
import json
import os
from pathlib import Path
import platform
import sys
import traceback
import uuid
import wave
from datetime import datetime

from PySide6.QtCore import Qt, QProcess, QProcessEnvironment, QUrl, qInstallMessageHandler
from PySide6.QtGui import QColor, QDesktopServices, QPainter
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox,
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout,
    QWidget)



from .session_trace import SessionTrace
from .conversion import ffmpeg_executable, prepare, publish
from .model import ProjectError


STYLE = '''
QWidget { background: #10141b; color: #e9edf1; font-family: "Segoe UI", "Arial"; font-size: 13px; }
QMainWindow, QScrollArea, QScrollArea > QWidget > QWidget { background: #10141b; }
QFrame#sidebar { background: #141a22; border-right: 1px solid #27313d; }
QFrame#card { background: #1a212c; border: 1px solid #303c4a; border-radius: 12px; }
QFrame#strip { background: #151c25; border: 1px solid #2b3745; border-radius: 8px; }
QLabel { background: transparent; border: none; }
QLabel#brand { font-size: 20px; font-weight: 750; color: #f6f8fa; }
QLabel#title { font-size: 30px; font-weight: 750; color: #f6f8fa; }
QLabel#section { font-size: 17px; font-weight: 700; }
QLabel#muted { color: #9aa8b7; font-size: 12px; }
QLabel#accent { color: #73dfc1; font-weight: 700; font-size: 11px; }
QLabel#warning { color: #eac77e; font-size: 12px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #111821; border: 1px solid #344150; border-radius: 6px; padding: 7px; min-height: 22px; selection-background-color: #288a7a; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid #70dfc2; }
QPushButton { background: #283441; border: 1px solid #3c4b5a; border-radius: 7px; padding: 9px 14px; font-weight: 600; }
QPushButton:hover { background: #354758; }
QPushButton:disabled { color: #687482; background: #252e37; }
QPushButton#nav { text-align: left; background: transparent; border: none; padding: 12px; color: #a3b2c1; }
QPushButton#nav:checked { background: #203b3b; color: #81e6ca; }
QPushButton#primary { background: #72dfbf; color: #10231f; border: none; padding: 12px 20px; font-weight: 750; }
QPushButton#primary:hover { background: #a2efd7; }
QPlainTextEdit { background: #0d131a; color: #afc1c7; border: 1px solid #2c3947; border-radius: 7px; font-family: Consolas, monospace; font-size: 11px; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QScrollBar:vertical { background: #10141b; width: 10px; }
QScrollBar::handle:vertical { background: #364555; border-radius: 4px; min-height: 30px; }
'''


def label(text, name=None):
    obj = QLabel(text)
    if name:
        obj.setObjectName(name)
    return obj


def card():
    frame = QFrame()
    frame.setObjectName('card')
    return frame


class Timeline(QWidget):
    """Illustrative clip ranges from WAV headers; never drawn as a waveform."""
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setMinimumHeight(118)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#141b24'))
        p.setPen(QColor('#8596a6'))
        p.drawText(15, 20, 'ПРЕДПРОСМОТР РАЗМЕЩЕНИЯ  ·  НЕ ВОЛНОВАЯ ФОРМА')
        left, width = 64, max(1, self.width() - 82)
        bpm = self.window.bpm.value()
        data = []
        for track in self.window.tracks:
            start = ((track['bar'].value()-1)*4 + track['beat'].value()-1 + track['tick'].value()/960) * 60/bpm
            try:
                a = int(track['start'].text() or '0')
                b = int(track['end'].text()) if track['end'].text() else track['frames']
                duration = max(0, b-a)/track['rate'] if b and track['rate'] else 0
            except ValueError:
                duration = 0
            data.append((start, duration))
        total = max(1.0, *(start+duration for start, duration in data))
        for i in range(5):
            x = left + width*i/4
            p.setPen(QColor('#334150')); p.drawLine(int(x), 34, int(x), 111)
            p.setPen(QColor('#8292a2')); p.drawText(int(x), 31, f'{total*i/4:.1f}s')
        for i, (start, duration) in enumerate(data):
            y = 43 + i*35
            p.setPen(QColor('#a7b6c4')); p.drawText(15, y+16, f'0{i+1}')
            if duration:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor('#56cbb0' if i == 0 else '#eab978'))
                p.drawRoundedRect(int(left+start/total*width), y, max(2, int(duration/total*width)), 22, 5, 5)
        p.end()


class MashupWindow(QMainWindow):
    def __init__(self, trace, conversion_dir=None):
        super().__init__()
        self.conversion_dir = Path(conversion_dir) if conversion_dir is not None else Path.home() / ".mashup-lab" / "converted"
        self.trace = trace
        self.process = None
        self.converter_process = None
        self.analysis_process = None
        self.engine_process = None
        self.engine_result = None
        self.converter_workspace = None
        self.converted_path = None
        self.convert_cancelled = False
        self._dialogs = []
        self.stdout = bytearray()
        self.stderr = bytearray()
        self.result_path = None
        self.tracks = []
        self.setWindowTitle('Mashup Lab · Студия')
        self.resize(1310, 920)
        self.setMinimumSize(900, 700)
        self._build()
        self.record('ui.ready')

    def record(self, event, **fields):
        row = self.trace.emit(event, **fields)
        if hasattr(self, 'activity'):
            detail = fields.get('message') or fields.get('error') or ''
            self.activity.appendPlainText(f"{row['time_utc'][11:19]}  {event} {str(detail)[:500]}")
            if self.trace.error:
                self.trace_status.setText('Трасса недоступна: ' + self.trace.error)
                self.trace_status.setObjectName('warning')
        return row

    def _build(self):
        root = QWidget(); self.setCentralWidget(root)
        outer = QHBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        side = QFrame(); side.setObjectName('sidebar'); side.setFixedWidth(205)
        sl = QVBoxLayout(side); sl.setContentsMargins(16,27,16,22); sl.setSpacing(9)
        sl.addWidget(label('◈  MASHUP', 'brand')); sl.addWidget(label('LAB  /  AUDIO STUDIO', 'accent'))
        sl.addSpacing(28); sl.addWidget(label('РАБОЧЕЕ ПРОСТРАНСТВО', 'muted'))
        self.nav = QButtonGroup(self); self.nav.setExclusive(True)
        for i, title in ((1, '1  Конвертация'), (4, '2  Обработка'), (0, '3  Мешап'), (2, '⚙   Параметры'), (3, '≡   Трасса')):
            button = QPushButton(title); button.setObjectName('nav'); button.setCheckable(True)
            self.nav.addButton(button, i); sl.addWidget(button)
        self.nav.button(1).setChecked(True); self.nav.idClicked.connect(self.switch_page)
        sl.addStretch(); sl.addWidget(label('ЭКСПЕРИМЕНТАЛЬНО', 'accent'))
        small = label('Конвертация отдельно\nот рендерера', 'muted'); small.setWordWrap(True); sl.addWidget(small)
        outer.addWidget(side)
        self.stack = QStackedWidget(); outer.addWidget(self.stack, 1)
        mashup_page = QWidget(); mashup_layout = QVBoxLayout(mashup_page); mashup_layout.setContentsMargins(0,0,0,0); mashup_layout.setSpacing(0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(); scroll.setWidget(body); mashup_layout.addWidget(scroll, 1); self.stack.addWidget(mashup_page)
        column = QVBoxLayout(body); column.setContentsMargins(34,26,34,30); column.setSpacing(18)
        header = QHBoxLayout(); title = QVBoxLayout(); title.addWidget(label('СОЗДАТЬ  /  НОВЫЙ ПРОЕКТ', 'accent')); title.addWidget(label('Два трека. Один мешап.', 'title')); title.addWidget(label('Выберите аудио, настройте расположение и соберите свой первый микс.', 'muted')); header.addLayout(title); header.addStretch()
        status = label('●  48 kHz  /  PCM WAV', 'accent'); header.addWidget(status); column.addLayout(header)
        self.controls = QWidget(); controls = QVBoxLayout(self.controls); controls.setContentsMargins(0,0,0,0); controls.setSpacing(16)
        tracks_header = QHBoxLayout(); tracks_header.addWidget(label('01  Исходники', 'section')); tracks_header.addStretch(); tracks_header.addWidget(label('МОНО ИЛИ СТЕРЕО  ·  16 / 24 / 32 BIT', 'muted')); controls.addLayout(tracks_header)
        for index in (1,2):
            controls.addWidget(self._track_card(index))
        config = card(); cl = QVBoxLayout(config); cl.setContentsMargins(18,16,18,16)
        row = QHBoxLayout(); row.addWidget(label('02  Размещение', 'section')); row.addStretch(); row.addWidget(label('СХЕМА ПО ГРАНИЦАМ КЛИПОВ', 'muted')); cl.addLayout(row)
        self.timeline = Timeline(self); cl.addWidget(self.timeline)
        note = label('Темп и формат экспорта находятся в разделе «Параметры».', 'muted'); note.setWordWrap(True); cl.addWidget(note)
        controls.addWidget(config)
        output = card(); ol = QVBoxLayout(output); ol.setContentsMargins(18,16,18,16)
        ol.addWidget(label('03  Куда сохранить', 'section'))
        ol.addWidget(label('Укажите новую папку: в ней появятся project.yaml, копии WAV и результат.', 'muted'))
        pathrow = QHBoxLayout(); self.output_dir = QLineEdit(str(Path.home() / ('Mashup-' + datetime.now().strftime('%Y%m%d-%H%M%S')))); self.output_dir.setObjectName('output_dir'); pathrow.addWidget(self.output_dir,1)
        choose = QPushButton('Выбрать родительскую папку'); choose.clicked.connect(self.choose_output); pathrow.addWidget(choose); ol.addLayout(pathrow)
        controls.addWidget(output); column.addWidget(self.controls)
        action = QHBoxLayout(); self.make = QPushButton('Создать мешап  →'); self.make.setObjectName('primary'); self.make.clicked.connect(self.run); action.addWidget(self.make)
        self.stop_render = QPushButton('Остановить'); self.stop_render.setEnabled(False); self.stop_render.clicked.connect(self.cancel_render); action.addWidget(self.stop_render)
        self.open_output = QPushButton('Открыть WAV'); self.open_output.setEnabled(False); self.open_output.clicked.connect(self.open_result); action.addWidget(self.open_output)
        self.run_status = label('Готов к работе', 'muted'); self.run_status.setWordWrap(True); action.addWidget(self.run_status,1)
        footer = QWidget(); footer_layout = QVBoxLayout(footer); footer_layout.setContentsMargins(18,8,18,8); footer_layout.addLayout(action); mashup_layout.addWidget(footer); column.addStretch()

        conversion_page, cv = self.page('ПОДГОТОВКА  /  КОНВЕРТАЦИЯ', 'Подготовить аудио',
                                        'Отдельная копия для рендерера · исходный файл не изменяется.')
        self.converter_controls = card(); form = QVBoxLayout(self.converter_controls); form.setContentsMargins(20,20,20,20); form.setSpacing(14)
        form.addWidget(label('01  Исходный аудиофайл', 'section'))
        row = QHBoxLayout(); self.conversion_input = QLineEdit(); self.conversion_input.setPlaceholderText('WAV, MP3 или другой локальный аудиофайл'); row.addWidget(self.conversion_input,1)
        pick = QPushButton('Обзор…'); pick.clicked.connect(self.choose_conversion_input); row.addWidget(pick); form.addLayout(row)
        form.addWidget(label('02  Папка конвертированных файлов', 'section'))
        folder = label(str(self.conversion_dir), 'muted'); folder.setWordWrap(True); folder.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); form.addWidget(folder)
        self.conversion_output = QLineEdit(); self.conversion_output.setReadOnly(True); self.conversion_output.setPlaceholderText('Имя файла будет создано автоматически'); form.addWidget(self.conversion_output)
        row = QHBoxLayout(); row.addWidget(label('Выход')); row.addWidget(label('48 000 Hz  ·  PCM 16-bit WAV', 'accent')); row.addSpacing(20); row.addWidget(label('Каналы'))
        self.conversion_channels = QComboBox(); self.conversion_channels.addItem('Стерео', 2); self.conversion_channels.addItem('Моно', 1); row.addWidget(self.conversion_channels); row.addStretch(); form.addLayout(row)
        hint = label('FFmpeg конвертирует первую аудиодорожку; сведение в моно и 16-bit могут изменить звук. Существующий файл не перезаписывается.', 'muted'); hint.setWordWrap(True); form.addWidget(hint)
        cv.addWidget(self.converter_controls)
        row = QHBoxLayout(); self.convert_button = QPushButton('Конвертировать  →'); self.convert_button.setObjectName('primary'); self.convert_button.clicked.connect(self.convert); row.addWidget(self.convert_button)
        self.cancel_conversion_button = QPushButton('Остановить'); self.cancel_conversion_button.setEnabled(False); self.cancel_conversion_button.clicked.connect(self.cancel_conversion); row.addWidget(self.cancel_conversion_button)
        self.conversion_status = label('Готово к подготовке', 'muted'); self.conversion_status.setWordWrap(True); row.addWidget(self.conversion_status,1); cv.addLayout(row)
        row = QHBoxLayout(); self.to_processing = QPushButton('Далее: обработка →'); self.to_processing.setEnabled(False); self.to_processing.clicked.connect(self.send_converted_to_processing); row.addWidget(self.to_processing); self.use_converted1 = QPushButton('Использовать как аудио 1'); self.use_converted2 = QPushButton('Использовать как аудио 2')
        for number, button in ((1,self.use_converted1),(2,self.use_converted2)):
            button.setEnabled(False); button.clicked.connect(lambda checked=False, n=number: self.use_converted(n)); row.addWidget(button)
        row.addStretch(); cv.addLayout(row); cv.addStretch(); self.stack.addWidget(conversion_page)

        settings_page, sv = self.page('ПРОЕКТ  /  ПАРАМЕТРЫ', 'Параметры проекта', 'Изменения действуют при следующем создании мешапа.')
        settings_card = card(); settings = QVBoxLayout(settings_card); settings.setContentsMargins(20,20,20,20); settings.setSpacing(14)
        row = QHBoxLayout(); row.addWidget(label('BPM проекта')); self.bpm = QDoubleSpinBox(); self.bpm.setRange(1,999); self.bpm.setDecimals(2); self.bpm.setValue(120); self.bpm.setFixedWidth(110); row.addWidget(self.bpm); row.addStretch(); settings.addLayout(row)
        note = label('BPM задаёт только разметку. Автосинхронизации и изменения темпа нет.', 'muted'); note.setWordWrap(True); settings.addWidget(note)
        row = QHBoxLayout(); row.addWidget(label('Разрядность выходного WAV')); self.depth = QComboBox(); self.depth.addItems(['24-bit', '16-bit']); row.addWidget(self.depth); row.addStretch(); settings.addLayout(row)
        self.verify = QCheckBox('Проверить повторный рендер'); self.verify.setChecked(True); settings.addWidget(self.verify)
        sv.addWidget(settings_card); sv.addStretch(); self.stack.addWidget(settings_page)

        trace_page, tv = self.page('ДИАГНОСТИКА  /  СОБЫТИЯ', 'Трасса действий', 'События и ошибки текущей сессии.')
        trace_card = card(); tl = QVBoxLayout(trace_card); tl.setContentsMargins(18,15,18,15)
        tr = QHBoxLayout(); tr.addWidget(label('Локальный журнал', 'section')); tr.addStretch(); open_logs = QPushButton('Открыть папку логов'); open_logs.clicked.connect(self.open_logs); tr.addWidget(open_logs); tl.addLayout(tr)
        self.trace_status = label(str(self.trace.path) if self.trace.path else 'Трасса недоступна: ' + str(self.trace.error), 'muted' if self.trace.path else 'warning'); self.trace_status.setWordWrap(True); self.trace_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); tl.addWidget(self.trace_status)
        privacy = label('Локальный JSONL содержит пути и параметры. Перед отправкой проверьте конфиденциальность.', 'muted'); privacy.setWordWrap(True); tl.addWidget(privacy)
        self.activity = QPlainTextEdit(); self.activity.setReadOnly(True); self.activity.setMaximumBlockCount(1000); self.activity.setMinimumHeight(280); tl.addWidget(self.activity); tv.addWidget(trace_card,1); self.stack.addWidget(trace_page)
        processing_page, pv = self.page('02 / ОБРАБОТКА', 'Обработка аудио', 'Отдельный шаг: анализ и подготовка копии перед мешапом.')
        self.processing_controls = card(); proc = QVBoxLayout(self.processing_controls); proc.setContentsMargins(20,20,20,20); proc.setSpacing(12)
        proc.addWidget(label('Исходный WAV', 'section'))
        row = QHBoxLayout(); self.processing_input = QLineEdit(); self.processing_input.setPlaceholderText('Выберите подготовленный 48 kHz WAV'); row.addWidget(self.processing_input, 1)
        choose_input = QPushButton('Обзор…'); choose_input.clicked.connect(self.choose_processing_input); row.addWidget(choose_input); proc.addLayout(row)
        proc.addWidget(label('Движок разделения', 'section'))
        self.engine_choice = QComboBox(); self.engine_choice.addItem('UVR MDX-Net · вокал / инструментал (CPU)', 'uvr-mdx-hq3'); proc.addWidget(self.engine_choice)
        self.engine_denoise = QCheckBox('Дополнительный проход MDX (медленнее)'); proc.addWidget(self.engine_denoise)
        hint = label('Модель разделяет вокал и инструментал; результат может содержать артефакты. Это не отдельное шумоподавление или удаление реверберации.', 'muted'); hint.setWordWrap(True); proc.addWidget(hint)
        self.separate_button = QPushButton('Разделить вокал и музыку'); self.separate_button.setObjectName('primary'); self.separate_button.clicked.connect(self.start_separation); proc.addWidget(self.separate_button)
        self.analysis_target = QComboBox(); self.analysis_target.addItem('Анализировать подготовленный файл', 'input'); proc.addWidget(self.analysis_target)
        self.analysis_info = label('BPM и тональность не определены', 'muted'); self.analysis_info.setWordWrap(True); proc.addWidget(self.analysis_info)
        self.analyze_button = QPushButton('Определить BPM и тональность'); self.analyze_button.clicked.connect(self.analyze_processing); proc.addWidget(self.analyze_button)
        pv.addWidget(self.processing_controls)
        self.processing_status = label('Ожидание файла', 'muted'); self.processing_status.setWordWrap(True); pv.addWidget(self.processing_status)
        self.stop_analysis = QPushButton('Остановить обработку / анализ'); self.stop_analysis.setEnabled(False); self.stop_analysis.clicked.connect(self.cancel_render); pv.addWidget(self.stop_analysis)
        row = QHBoxLayout(); self.stem_choice = QComboBox(); self.stem_choice.addItem('Вокал', 'vocals'); self.stem_choice.addItem('Инструментал', 'instrumental'); self.stem_choice.setEnabled(False); row.addWidget(self.stem_choice)
        self.stem_buttons = []
        for number in (1, 2):
            button = QPushButton(f'Передать результат как аудио {number} →'); button.setEnabled(False); button.clicked.connect(lambda checked=False, n=number: self.use_stem(n)); self.stem_buttons.append(button); row.addWidget(button)
        pv.addLayout(row)
        row = QHBoxLayout()
        for number in (1, 2):
            button = QPushButton(f'Передать исходный WAV как аудио {number} →'); button.clicked.connect(lambda checked=False, n=number: self.use_processing_input(n)); row.addWidget(button)
        pv.addLayout(row); pv.addStretch(); self.stack.addWidget(processing_page); self.stack.setCurrentIndex(1)
        self.bpm.valueChanged.connect(lambda v: self.changed('bpm', v)); self.depth.currentTextChanged.connect(lambda v: self.changed('bit_depth', v)); self.verify.toggled.connect(lambda v: self.changed('verify_repeat', v)); self.output_dir.editingFinished.connect(lambda: self.changed('output_dir', self.output_dir.text()))
        self.conversion_input.editingFinished.connect(lambda: self.changed('conversion_input', self.conversion_input.text()))
        self.conversion_output.editingFinished.connect(lambda: self.changed('conversion_output', self.conversion_output.text()))
        self.conversion_channels.currentTextChanged.connect(lambda v: self.changed('conversion_channels', v))
        self.processing_input.textChanged.connect(self.processing_input_changed)
        self.analysis_target.currentIndexChanged.connect(lambda _: self.analysis_info.setText('BPM и тональность не определены'))

    def page(self, kicker, title, subtitle):
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(); scroll.setWidget(body)
        layout = QVBoxLayout(body); layout.setContentsMargins(34,26,34,30); layout.setSpacing(18)
        layout.addWidget(label(kicker,'accent')); layout.addWidget(label(title,'title')); layout.addWidget(label(subtitle,'muted'))
        return scroll, layout

    def switch_page(self, index):
        self.stack.setCurrentIndex(index)
        self.nav.button(index).setChecked(True)
        self.record('ui.page_changed', page=('mashup','conversion','settings','trace','processing')[index])

    def _track_card(self, number):
        frame = card(); box = QVBoxLayout(frame); box.setContentsMargins(18,15,18,17); box.setSpacing(12)
        head = QHBoxLayout(); head.addWidget(label(f'АУДИО 0{number}', 'accent' if number == 1 else 'warning')); head.addWidget(label('Вокал / инструментал' if number == 1 else 'Инструментал / вокал', 'section')); head.addStretch()
        info = label('ФАЙЛ НЕ ВЫБРАН', 'muted'); head.addWidget(info); box.addLayout(head)
        files = QHBoxLayout(); path = QLineEdit(); path.setObjectName(f'audio{number}'); path.setPlaceholderText('Выберите WAV-файл 48 kHz'); files.addWidget(path,1)
        select = QPushButton('Обзор…'); select.clicked.connect(lambda: self.choose_file(number)); files.addWidget(select)
        prepare_button = QPushButton('В конвертер'); prepare_button.clicked.connect(lambda: self.send_to_conversion(number)); files.addWidget(prepare_button); box.addLayout(files)
        opts = QGridLayout(); opts.setHorizontalSpacing(12); opts.setVerticalSpacing(6)
        def spin(name, low, high, value, decimal=False):
            w = QDoubleSpinBox() if decimal else QSpinBox()
            w.setRange(low,high); w.setValue(value)
            if decimal: w.setDecimals(2); w.setSingleStep(0.1 if name == 'pan' else 1)
            w.setObjectName(f'{name}{number}'); w.valueChanged.connect(lambda v: self.changed(f'{name}{number}',v))
            return w
        bar = spin('bar',1,9999,1); beat = spin('beat',1,4,1); tick = spin('tick',0,959,0)
        gain = spin('gain',-120,24,0,True); pan = spin('pan',-1,1,0,True)
        start = QLineEdit('0'); start.setObjectName(f'start{number}'); end = QLineEdit(); end.setObjectName(f'end{number}'); end.setPlaceholderText('до конца')
        fade_in = spin('fade_in',0,2147483647,0); fade_out = spin('fade_out',0,2147483647,0)
        fields = [('Такт',bar),('Доля',beat),('Тик',tick),('Gain · dB',gain),('Pan',pan),('От · frame',start),('До · frame',end),('Fade in · frames',fade_in),('Fade out · frames',fade_out)]
        for index,(title,widget) in enumerate(fields):
            row, col = divmod(index, 3)
            opts.addWidget(label(title,'muted'),row*2,col); opts.addWidget(widget,row*2+1,col)
        box.addLayout(opts)
        track = {'path':path,'info':info,'bar':bar,'beat':beat,'tick':tick,'gain':gain,'pan':pan,'start':start,'end':end,'fade_in':fade_in,'fade_out':fade_out,'frames':0,'rate':0}
        self.tracks.append(track)
        path.editingFinished.connect(lambda: self.read_header(number))
        start.editingFinished.connect(lambda: self.changed(f'start{number}',start.text()))
        end.editingFinished.connect(lambda: self.changed(f'end{number}',end.text()))
        return frame

    def changed(self, field, value):
        self.record('ui.value_changed', field=field, value=value)
        if hasattr(self, 'timeline'):
            self.timeline.update()

    def file_picker(self, title, mode, callback, trace_event, name_filter=None):
        # Non-modal picker: settings and workflows remain in the main window.
        dialog = QFileDialog(self, title)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setFileMode(mode)
        if name_filter:
            dialog.setNameFilter(name_filter)
        self._dialogs.append(dialog)
        def selected(path):
            self.record(trace_event, selected=path)
            callback(path)
        def closed(result):
            if not result:
                self.record(trace_event, selected=None)
            if dialog in self._dialogs:
                self._dialogs.remove(dialog)
            dialog.deleteLater()
        dialog.fileSelected.connect(selected)
        dialog.finished.connect(closed)
        dialog.show()

    def choose_file(self, number):
        self.record('ui.choose_file', track=number)
        def chosen(path):
            self.tracks[number-1]['path'].setText(path); self.read_header(number)
        self.file_picker(f'Выберите аудио {number}', QFileDialog.FileMode.ExistingFile,
                         chosen, 'ui.file_dialog_result', 'WAV (*.wav);;Все файлы (*)')

    def send_to_conversion(self, number):
        path = self.tracks[number-1]['path'].text().strip()
        self.record('ui.send_to_conversion', track=number, path=path)
        if path:
            self.set_conversion_input(path)
        self.switch_page(1)

    def set_conversion_input(self, path):
        self.conversion_input.setText(path)
        self.conversion_output.clear()
        self.changed('conversion_input', path)

    def choose_conversion_input(self):
        self.record('ui.choose_conversion_input')
        self.file_picker('Выберите исходный аудиофайл', QFileDialog.FileMode.ExistingFile,
                         self.set_conversion_input, 'ui.conversion_input_dialog_result',
                         'Аудио (*.wav *.mp3 *.flac *.m4a *.aac *.ogg *.opus *.aif *.aiff);;Все файлы (*)')

    def read_header(self, number):
        t = self.tracks[number-1]; path = t['path'].text().strip(); t['frames'] = 0; t['rate'] = 0
        try:
            with wave.open(path, 'rb') as wav:
                t['frames'] = wav.getnframes(); t['rate'] = wav.getframerate()
                info = f'{wav.getframerate()} Hz  ·  {wav.getnchannels()} ch  ·  {wav.getnframes()/wav.getframerate():.2f} сек'
                if wav.getframerate() != 48000 or wav.getnchannels() not in (1,2) or wav.getsampwidth() not in (2,3,4):
                    info += '  ·  НЕПОДДЕРЖИВАЕМЫЙ ФОРМАТ'
                t['info'].setText(info)
            self.record('ui.source_loaded', track=number, path=path, frames=t['frames'], metadata=info)
        except (OSError, ValueError, wave.Error, EOFError, ZeroDivisionError) as exc:
            t['info'].setText('НЕ УДАЛОСЬ ПРОЧИТАТЬ WAV'); self.record('ui.source_error', track=number, path=path, error=str(exc))
        if hasattr(self,'timeline'): self.timeline.update()

    def choose_output(self):
        self.record('ui.choose_output_parent')
        def chosen(parent):
            self.output_dir.setText(str(Path(parent) / ('Mashup-' + datetime.now().strftime('%Y%m%d-%H%M%S'))))
            self.changed('output_dir', self.output_dir.text())
        self.file_picker('Выберите родительскую папку', QFileDialog.FileMode.Directory,
                         chosen, 'ui.output_dialog_result')

    def convert(self):
        self.record('conversion.requested', source=self.conversion_input.text().strip(),
                    output=self.conversion_output.text().strip(), channels=self.conversion_channels.currentData())
        if self.converter_process is not None or self.process is not None or self.analysis_process is not None or self.engine_process is not None:
            self.conversion_status.setText('Дождитесь завершения текущей операции.'); return
        self.converted_path = None
        self.to_processing.setEnabled(False); self.use_converted1.setEnabled(False); self.use_converted2.setEnabled(False)
        source = self.conversion_input.text().strip()
        if not source:
            self.conversion_status.setText('Укажите исходный файл.')
            self.record('conversion.validation_error', error='Пустой путь'); return
        try:
            exe = ffmpeg_executable()
            self.conversion_dir.mkdir(parents=True, exist_ok=True)
            output = str(self.conversion_dir / ('converted-' + uuid.uuid4().hex + '.wav'))
            self.conversion_output.setText(output)
            self.record('conversion.target_selected', output=output)
            workspace, stage, args = prepare(source, output, self.conversion_channels.currentData())
        except (ProjectError, OSError) as exc:
            self.conversion_status.setText(str(exc)); self.record('conversion.validation_error', error=str(exc)); return
        self.converter_workspace = workspace; self.conversion_stage = stage
        self.conversion_target = Path(output).expanduser().absolute()
        self.conversion_channel_count = self.conversion_channels.currentData()
        self.conversion_stderr = bytearray(); self.conversion_stdout = bytearray(); self.convert_cancelled = False
        self.converter_controls.setEnabled(False); self.convert_button.setEnabled(False); self.make.setEnabled(False)
        self.cancel_conversion_button.setEnabled(True); self.conversion_status.setText('Конвертация…')
        self.converter_process = QProcess(self)
        self.converter_process.readyReadStandardOutput.connect(self.read_conversion_stdout)
        self.converter_process.readyReadStandardError.connect(self.read_conversion_stderr)
        self.converter_process.finished.connect(self.conversion_finished)
        self.converter_process.errorOccurred.connect(self.conversion_process_error)
        self.record('conversion.started', executable=str(exe), arguments=args, output=str(self.conversion_target))
        self.converter_process.start(str(exe), args)

    def read_conversion_stdout(self):
        if not self.converter_process: return
        self.conversion_stdout.extend(bytes(self.converter_process.readAllStandardOutput()))
        while b'\n' in self.conversion_stdout:
            line, _, rest = self.conversion_stdout.partition(b'\n'); self.conversion_stdout = bytearray(rest)
            text = line.decode('utf-8','replace').strip()
            if text.startswith(('out_time=', 'progress=')):
                self.record('conversion.progress', message=text)
                if text.startswith('out_time='): self.conversion_status.setText('Конвертация · ' + text[9:])

    def read_conversion_stderr(self):
        if not self.converter_process: return
        self.conversion_stderr.extend(bytes(self.converter_process.readAllStandardError()))
        while b'\n' in self.conversion_stderr:
            line, _, rest = self.conversion_stderr.partition(b'\n'); self.conversion_stderr = bytearray(rest)
            self.record('conversion.ffmpeg', message=line.decode('utf-8','replace').strip())

    def cancel_conversion(self):
        if self.converter_process:
            self.convert_cancelled = True; self.record('conversion.cancel_requested')
            self.conversion_status.setText('Остановка…'); self.converter_process.kill()

    def conversion_process_error(self, error):
        if not self.converter_process: return
        message = self.converter_process.errorString(); self.record('conversion.process_error', error=message)
        if error == QProcess.ProcessError.FailedToStart:
            self.conversion_status.setText('Не удалось запустить FFmpeg: ' + message)
            self.cleanup_conversion()

    def cleanup_conversion(self):
        if self.converter_process:
            self.converter_process.deleteLater(); self.converter_process = None
        if self.converter_workspace:
            try:
                self.converter_workspace.cleanup()
            except OSError as exc:
                self.record('conversion.cleanup_error', error=str(exc))
            self.converter_workspace = None
        self.converter_controls.setEnabled(True); self.convert_button.setEnabled(True); self.cancel_conversion_button.setEnabled(False)
        self.make.setEnabled(True)

    def conversion_finished(self, code, exit_status):
        if not self.converter_process: return
        self.read_conversion_stdout(); self.read_conversion_stderr()
        if self.conversion_stderr:
            self.record('conversion.ffmpeg', message=bytes(self.conversion_stderr).decode('utf-8','replace'))
            self.conversion_stderr.clear()
        try:
            if self.convert_cancelled:
                self.record('conversion.cancelled', exit_code=code); self.conversion_status.setText('Конвертация остановлена. Исходник не изменён.')
            elif code != 0 or exit_status != QProcess.ExitStatus.NormalExit:
                self.record('conversion.failed', exit_code=code, exit_status=str(exit_status))
                self.conversion_status.setText('Ошибка FFmpeg. Подробности в разделе «Трасса».')
            else:
                info = publish(self.conversion_stage, self.conversion_target, self.conversion_channel_count)
                self.converted_path = str(self.conversion_target)
                self.to_processing.setEnabled(True); self.use_converted1.setEnabled(True); self.use_converted2.setEnabled(True)
                self.record('conversion.completed', output=self.converted_path, **info)
                self.conversion_status.setText(f"Готово · {info['frames']/48000:.2f} сек · {info['channels']} канал(а)")
        except ProjectError as exc:
            self.record('conversion.publish_error', error=str(exc)); self.conversion_status.setText(str(exc))
        finally:
            self.record('conversion.finished', exit_code=code, exit_status=str(exit_status))
            self.cleanup_conversion()

    def use_converted(self, number):
        if not self.converted_path: return
        self.record('conversion.use_output', track=number, path=self.converted_path)
        self.tracks[number-1]['path'].setText(self.converted_path)
        self.read_header(number); self.run_status.setText('Файл выбран. Проверьте диапазон клипа перед рендером.'); self.switch_page(0)

    def processing_input_changed(self, path):
        self.analysis_info.setText('BPM и тональность не определены')
        self.engine_result = None
        self.analysis_target.clear(); self.analysis_target.addItem('Анализировать подготовленный файл', 'input')
        self.stem_choice.setEnabled(False)
        for button in self.stem_buttons: button.setEnabled(False)
        self.record('processing.input_changed', path=path)

    def send_converted_to_processing(self):
        if self.converted_path:
            self.processing_input.setText(self.converted_path)
            self.analysis_info.setText('BPM и тональность не определены')
            self.record('processing.input_from_conversion', path=self.converted_path)
            self.switch_page(4)

    def choose_processing_input(self):
        self.file_picker('Выберите подготовленный WAV', QFileDialog.FileMode.ExistingFile,
                         self.set_processing_input, 'ui.processing_dialog_result', 'WAV (*.wav);;Все файлы (*)')

    def set_processing_input(self, path):
        self.processing_input.setText(path)
        self.analysis_info.setText('BPM и тональность не определены')
        self.record('processing.input_selected', path=path)

    def use_processing_input(self, number):
        path = self.processing_input.text().strip()
        if not Path(path).is_file():
            self.processing_status.setText('Выберите существующий WAV.'); return
        self.tracks[number-1]['path'].setText(path); self.read_header(number)
        self.record('processing.use_input', path=path, track=number)
        self.switch_page(0)

    def start_separation(self):
        if self.process or self.converter_process or self.analysis_process or self.engine_process:
            self.processing_status.setText('Дождитесь завершения текущей операции.'); return
        source = self.processing_input.text().strip()
        if not source or not Path(source).is_file():
            self.processing_status.setText('Выберите существующий подготовленный WAV.'); return
        root = Path(__file__).resolve().parent.parent
        python = root / '.venv-separation' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if not python.is_file():
            self.processing_status.setText('Движок не установлен. Откройте Mashup-Lab.bat и выберите пункт 9.')
            self.record('processing.engine_missing', python=str(python)); return
        try:
            exe = ffmpeg_executable()
            output_root = Path.home() / '.mashup-lab' / 'processed'
            output_root.mkdir(parents=True, exist_ok=True)
            target = output_root / ('separation-' + uuid.uuid4().hex)
        except (OSError, ProjectError) as exc:
            self.processing_status.setText(str(exc)); self.record('processing.validation_error', error=str(exc)); return
        self.engine_result = None; self.stem_choice.setEnabled(False)
        self.analysis_target.clear(); self.analysis_target.addItem('Анализировать подготовленный файл', 'input')
        for button in self.stem_buttons: button.setEnabled(False)
        self.engine_stdout = bytearray(); self.engine_stderr = bytearray()
        args = ['-m','mashup.separation','--input', source,'--output-dir',str(target),'--ffmpeg',str(exe)]
        if self.engine_denoise.isChecked(): args.append('--denoise')
        self.engine_process = QProcess(self); self.engine_process.setWorkingDirectory(str(root))
        env = QProcessEnvironment.systemEnvironment(); env.insert('PYTHONUTF8', '1'); self.engine_process.setProcessEnvironment(env)
        self.engine_process.readyReadStandardOutput.connect(self.read_engine_stdout)
        self.engine_process.readyReadStandardError.connect(self.read_engine_stderr)
        self.engine_process.finished.connect(self.engine_finished)
        self.engine_process.errorOccurred.connect(self.engine_error)
        self.processing_controls.setEnabled(False); self.stop_analysis.setEnabled(True); self.make.setEnabled(False); self.convert_button.setEnabled(False)
        self.processing_status.setText('Разделение… Это может занять несколько минут. Файлы: ' + str(target))
        self.record('processing.started', executable=str(python), arguments=args)
        self.engine_process.start(str(python), args)

    def read_engine_stdout(self):
        if self.engine_process: self.engine_stdout.extend(bytes(self.engine_process.readAllStandardOutput()))

    def read_engine_stderr(self):
        if not self.engine_process: return
        data = bytes(self.engine_process.readAllStandardError())
        self.engine_stderr.extend(data)
        while b'\n' in self.engine_stderr:
            line, _, rest = self.engine_stderr.partition(b'\n'); self.engine_stderr = bytearray(rest)
            self.record('processing.engine_log', message=line.decode('utf-8','replace').strip())

    def engine_cleanup(self):
        self.engine_process.deleteLater(); self.engine_process = None
        self.processing_controls.setEnabled(True); self.stop_analysis.setEnabled(False); self.make.setEnabled(True); self.convert_button.setEnabled(True)

    def engine_error(self, error):
        if self.engine_process and error == QProcess.ProcessError.FailedToStart:
            message = self.engine_process.errorString(); self.record('processing.process_error', error=message)
            self.processing_status.setText('Не удалось запустить движок: ' + message); self.engine_cleanup()

    def engine_finished(self, code, status):
        if not self.engine_process: return
        self.read_engine_stdout(); self.read_engine_stderr()
        if self.engine_stderr: self.record('processing.engine_log', message=bytes(self.engine_stderr).decode('utf-8','replace'))
        if code == 0 and status == QProcess.ExitStatus.NormalExit:
            try:
                report = json.loads(bytes(self.engine_stdout).decode('utf-8'))
                if not all(Path(report['outputs'][key]).is_file() for key in ('vocals','instrumental')): raise ValueError('Выходные файлы отсутствуют')
                self.engine_result = report['outputs']; self.stem_choice.setEnabled(True)
                self.analysis_target.addItem('Анализировать вокал', 'vocals'); self.analysis_target.addItem('Анализировать инструментал', 'instrumental')
                for button in self.stem_buttons: button.setEnabled(True)
                self.processing_status.setText('Готово: вокал и инструментал. Проверьте результат на слух.')
                self.record('processing.completed', report=report)
            except (ValueError, KeyError, TypeError) as exc:
                self.processing_status.setText('Не удалось разобрать результат. См. трассу.'); self.record('processing.invalid_report', error=str(exc))
        else:
            self.processing_status.setText('Обработка остановлена или завершилась с ошибкой. См. трассу; временные файлы могут остаться.')
            self.record('processing.failed', exit_code=code, exit_status=str(status))
        self.engine_cleanup()

    def use_stem(self, number):
        key = self.stem_choice.currentData()
        if not self.engine_result or key not in self.engine_result: return
        path = self.engine_result[key]
        self.tracks[number-1]['path'].setText(path); self.read_header(number)
        self.record('processing.use_output', stem=key, path=path, track=number)
        self.switch_page(0)

    def analyze_processing(self):
        if self.process or self.converter_process or self.analysis_process or self.engine_process:
            self.processing_status.setText('Дождитесь завершения текущей операции.'); return
        selected = self.analysis_target.currentData()
        path = self.processing_input.text().strip() if selected == 'input' else (self.engine_result or {}).get(selected, '')
        if not path:
            self.analysis_info.setText('Выберите файл.')
            self.record('analysis.validation_error', error='Пустой путь'); return
        self.analysis_stdout = bytearray(); self.analysis_stderr = bytearray()
        self.analysis_info.setText('Анализ… Первый запуск может занять время.')
        self.analysis_process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment(); env.insert('PYTHONUTF8', '1'); self.analysis_process.setProcessEnvironment(env)
        self.analysis_process.readyReadStandardOutput.connect(self.read_analysis_stdout)
        self.analysis_process.readyReadStandardError.connect(self.read_analysis_stderr)
        self.analysis_process.finished.connect(self.analysis_finished)
        self.analysis_process.errorOccurred.connect(self.analysis_error)
        self.processing_controls.setEnabled(False); self.stop_analysis.setEnabled(True); self.make.setEnabled(False); self.convert_button.setEnabled(False)
        args = ['-m', 'mashup.audio_analysis', path]
        self.record('analysis.started', source=path, executable=sys.executable, arguments=args)
        self.analysis_process.start(sys.executable, args)

    def read_analysis_stdout(self):
        if self.analysis_process:
            self.analysis_stdout.extend(bytes(self.analysis_process.readAllStandardOutput()))

    def read_analysis_stderr(self):
        if self.analysis_process:
            self.analysis_stderr.extend(bytes(self.analysis_process.readAllStandardError()))

    def analysis_error(self, error):
        if self.analysis_process and error == QProcess.ProcessError.FailedToStart:
            message = self.analysis_process.errorString()
            self.record('analysis.process_error', error=message)
            self.analysis_info.setText('Не удалось начать анализ: ' + message)
            self.analysis_cleanup()

    def analysis_cleanup(self):
        self.analysis_process.deleteLater(); self.analysis_process = None
        self.processing_controls.setEnabled(True); self.stop_analysis.setEnabled(False); self.make.setEnabled(True); self.convert_button.setEnabled(True)

    def analysis_finished(self, code, status):
        if not self.analysis_process: return
        self.read_analysis_stdout(); self.read_analysis_stderr()
        stderr = bytes(self.analysis_stderr).decode('utf-8', 'replace')
        if stderr: self.record('analysis.stderr', message=stderr[-10000:])
        info = self.analysis_info
        if code == 0 and status == QProcess.ExitStatus.NormalExit:
            try:
                data = json.loads(bytes(self.analysis_stdout).decode('utf-8'))
                bpm = data['bpm']; key = data['key'] or {}
                bpm_text = f'{bpm:.1f}' if bpm is not None else 'не определён'
                key_text = (str(key.get('name')) + ' ' + str(key.get('mode'))) if key.get('name') else 'не определена'
                if key.get('ambiguous'): key_text += ' (неоднозначно)'
                info.setText(f"BPM: {bpm_text} · Тональность: {key_text} · {data['note']}")
                self.record('analysis.completed', result=data)
            except (ValueError, TypeError, KeyError) as exc:
                info.setText('Ошибка ответа анализатора. См. трассу.')
                self.record('analysis.invalid_report', error=str(exc))
        else:
            info.setText('Анализ остановлен или завершился с ошибкой. См. трассу.')
            self.record('analysis.failed', exit_code=code, exit_status=str(status))
        self.analysis_cleanup()

    def cancel_render(self):
        if self.engine_process:
            self.record('processing.cancel_requested'); self.engine_process.kill(); return
        if self.analysis_process:
            self.record('analysis.cancel_requested'); self.analysis_process.kill(); return
        if self.process:
            self.record('backend.cancel_requested')
            self.run_status.setText('Остановка… Папка проекта может остаться неполной.')
            self.process.kill()

    def run(self):
        self.record('ui.render_clicked')
        if self.process is not None or self.converter_process is not None or self.analysis_process is not None or self.engine_process is not None:
            self.run_status.setText('Дождитесь завершения текущей операции.'); return
        paths = [t['path'].text().strip() for t in self.tracks]
        target = self.output_dir.text().strip()
        if not all(paths) or not target:
            self.record('ui.validation_error', error='Выберите оба WAV и новую папку проекта')
            self.run_status.setText('Выберите оба WAV и новую папку проекта'); return
        args = ['-m','mashup','quick-mashup',*paths,'--project-dir',target,
                '--bpm',f'{self.bpm.value():.2f}','--bit-depth',self.depth.currentText().split('-')[0]]
        for number,t in enumerate(self.tracks,1):
            args += [f'--bar{number}',str(t['bar'].value()),f'--beat{number}',str(t['beat'].value()),f'--tick{number}',str(t['tick'].value()),
                     f'--gain{number}',f"{t['gain'].value():.2f}",f'--pan{number}',f"{t['pan'].value():.2f}",
                     f'--start{number}',t['start'].text().strip(),f'--fade-in{number}',str(t['fade_in'].value()),f'--fade-out{number}',str(t['fade_out'].value())]
            if t['end'].text().strip(): args += [f'--end{number}',t['end'].text().strip()]
        if self.verify.isChecked(): args.append('--verify-repeat')
        self.stdout.clear(); self.stderr.clear(); self.result_path = None
        self.open_output.setEnabled(False); self.controls.setEnabled(False); self.make.setEnabled(False); self.convert_button.setEnabled(False); self.stop_render.setEnabled(True); self.run_status.setText('Обработка…')
        self.process = QProcess(self); env = QProcessEnvironment.systemEnvironment(); env.insert('MASHUP_GUI_TRACE','1'); env.insert('PYTHONUTF8','1'); self.process.setProcessEnvironment(env)
        self.process.readyReadStandardOutput.connect(self.read_stdout); self.process.readyReadStandardError.connect(self.read_stderr)
        self.process.finished.connect(self.finished); self.process.errorOccurred.connect(self.process_error)
        self.record('backend.start', executable=sys.executable, arguments=args)
        self.process.start(sys.executable, args)

    def read_stdout(self):
        if self.process: self.stdout.extend(bytes(self.process.readAllStandardOutput()))

    def read_stderr(self):
        if not self.process: return
        self.stderr.extend(bytes(self.process.readAllStandardError()))
        while b'\n' in self.stderr:
            line, _, rest = self.stderr.partition(b'\n'); self.stderr = bytearray(rest)
            self._stderr_line(line)

    def _stderr_line(self, line):
        text = line.decode('utf-8','replace')
        if text.startswith('@@MASHUP_TRACE@@'):
            try:
                data = json.loads(text[len('@@MASHUP_TRACE@@'):]); event = data.pop('event')
                self.record('backend.'+event, **data); return
            except (ValueError, KeyError, TypeError): pass
        self.record('backend.stderr', message=text)

    def process_error(self, error):
        if not self.process: return
        message = self.process.errorString(); self.record('backend.process_error', error=message)
        if error == QProcess.ProcessError.FailedToStart:
            self.process.deleteLater(); self.process = None; self.controls.setEnabled(True); self.make.setEnabled(True); self.convert_button.setEnabled(True); self.stop_render.setEnabled(False)
            self.run_status.setText('Не удалось запустить рендер: ' + message)

    def finished(self, code, exit_status):
        self.read_stdout(); self.read_stderr()
        if self.stderr: self._stderr_line(bytes(self.stderr)); self.stderr.clear()
        text = bytes(self.stdout).decode('utf-8','replace')
        if code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
            try:
                report = json.loads(text); self.result_path = report['output']; stats = report['render']
                self.open_output.setEnabled(True)
                self.run_status.setText(f"Готово · {stats['frames']/48000:.2f} сек · peak {stats['peak']:.3f} · scale {stats['scale']:.3f}")
                self.record('backend.success', report=report)
            except (ValueError, KeyError, TypeError) as exc:
                self.run_status.setText('Ошибка разбора ответа рендера'); self.record('backend.invalid_report', error=str(exc), stdout=text)
        else:
            self.run_status.setText(f'Ошибка рендера (код {code}). Подробности — в трассе.')
            self.record('backend.failed', exit_code=code, exit_status=str(exit_status), stdout=text)
        self.record('backend.finished', exit_code=code, exit_status=str(exit_status))
        self.process.deleteLater(); self.process = None; self.controls.setEnabled(True); self.make.setEnabled(True); self.convert_button.setEnabled(True); self.stop_render.setEnabled(False)

    def open_result(self):
        self.record('ui.open_result', path=self.result_path)
        if self.result_path and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.result_path).resolve()))):
            self.run_status.setText('Не удалось открыть WAV; найдите его в папке проекта.')
            self.record('ui.open_result_failed', path=self.result_path)

    def open_logs(self):
        self.record('ui.open_logs')
        if not self.trace.path or not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.trace.path.parent))):
            self.run_status.setText('Не удалось открыть папку трассы.')
            self.record('ui.open_logs_failed')

    def closeEvent(self, event):
        busy = self.process is not None or self.converter_process is not None or self.analysis_process is not None or self.engine_process is not None
        self.record('ui.close_requested', busy=busy)
        if busy:
            message = 'Сначала дождитесь завершения операции или нажмите «Остановить» в её разделе.'
            self.run_status.setText(message); self.conversion_status.setText(message)
            self.record('ui.close_blocked', message=message)
            self.switch_page(1 if self.converter_process is not None else 4 if self.analysis_process is not None or self.engine_process is not None else 0)
            event.ignore(); return
        self.record('ui.closed')
        event.accept()


def main(trace=None):
    if trace is None:
        trace = SessionTrace()
        trace.emit('application.start', python=sys.version, platform=platform.platform(), argv=sys.argv, cwd=os.getcwd())
    trace.emit('application.qt_loaded', pyside=__import__('PySide6').__version__)
    old_hook = sys.excepthook
    def exception_hook(kind, value, tb):
        trace.emit('python.unhandled_exception', traceback=''.join(traceback.format_exception(kind,value,tb)))
        old_hook(kind,value,tb)
    sys.excepthook = exception_hook
    def qt_message(mode, context, message):
        trace.emit('qt.message', severity=str(mode), message=message, file=context.file, line=context.line)
    qInstallMessageHandler(qt_message)
    try:
        app = QApplication(sys.argv[:1]); app.setApplicationName('Mashup Lab'); app.setStyleSheet(STYLE)
        window = MashupWindow(trace); window.show()
        code = app.exec()
        trace.emit('application.exit', exit_code=code)
        return code
    except Exception:
        trace.emit('application.error', traceback=traceback.format_exc())
        raise
    finally:
        qInstallMessageHandler(None); sys.excepthook = old_hook
