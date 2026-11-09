"""Real UVR inference smoke test, intended for the Windows hosted runner."""
import hashlib
import logging
import os
from pathlib import Path
import shutil
import sys
import tempfile
import wave
import struct

import imageio_ffmpeg
from audio_separator.separator import Separator

EXPECTED = '317554b07fe1ea5279a77f2b1520a41ea4b93432560c4ffd08792c30fddf9adc'
version = sys.argv[1]
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp); model_dir = root / 'models'; model_dir.mkdir()
    model = Path(os.environ['RUNNER_TEMP']) / 'model.onnx'
    assert hashlib.sha256(model.read_bytes()).hexdigest() == EXPECTED
    shutil.copyfile(model, model_dir / 'UVR-MDX-NET-Inst_HQ_3.onnx')
    shutil.copyfile(imageio_ffmpeg.get_ffmpeg_exe(), root / 'ffmpeg.exe')
    os.environ['PATH'] = str(root) + os.pathsep + os.environ['PATH']
    source = root / 'input.wav'
    with wave.open(str(source), 'wb') as w:
        w.setparams((1,2,44100,0,'NONE','not compressed'))
        w.writeframes(struct.pack('<44100h', *([1000, -1000] * 22050)))
    out = root / 'out'; out.mkdir()
    separator = Separator(log_level=logging.INFO, model_file_dir=str(model_dir), output_dir=str(out), output_format='WAV')
    if version == '0.12.0': separator.load_model('UVR-MDX-NET-Inst_HQ_3')
    else: separator.load_model('UVR-MDX-NET-Inst_HQ_3.onnx')
    files = separator.separate(str(source))
    print('files:', files)
    assert len(files) == 2
    for name in files:
        path = Path(name)
        if not path.is_absolute(): path = out / path
        assert path.is_file(), path
        with wave.open(str(path)) as w:
            assert w.getnframes() > 0 and w.getnchannels() in (1,2)
    print('REAL CPU INFERENCE OK', flush=True)
