"""Real model inference through the application adapter on Windows."""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import wave
import struct

import imageio_ffmpeg
from mashup import model_store
from mashup.separation import separate

expected = model_store.ASSETS['UVR-MDX-NET-Inst_HQ_3.onnx'][1]
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp); model_dir = root / 'models'; model_dir.mkdir()
    model = Path(os.environ['RUNNER_TEMP']) / 'model.onnx'
    assert hashlib.sha256(model.read_bytes()).hexdigest() == expected
    shutil.copyfile(model, model_dir / 'UVR-MDX-NET-Inst_HQ_3.onnx')
    model_store.install(model_dir)
    assert model_store.check(model_dir)
    source = root / 'input.wav'
    with wave.open(str(source), 'wb') as w:
        w.setparams((1,2,48000,0,'NONE','not compressed'))
        w.writeframes(struct.pack('<48000h', *([1000, -1000] * 24000)))
    original = hashlib.sha256(source.read_bytes()).hexdigest()
    result = separate(source, root / 'processed', imageio_ffmpeg.get_ffmpeg_exe(), model_dir=model_dir)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original
    for stem in ('vocals', 'instrumental'):
        with wave.open(result['outputs'][stem]) as w:
            assert w.getnframes() > 0 and (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (48000, 2, 2)
    print('REAL CPU PIPELINE OK', flush=True)
