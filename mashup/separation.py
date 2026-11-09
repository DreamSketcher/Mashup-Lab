"""Adapter for the external UVR MDX engine; it never modifies source audio."""
import argparse
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import wave

from . import model_store
from .conversion import prepare, publish


def separate(source, target, ffmpeg, denoise=False, model_dir=None):
    source = Path(source).expanduser().absolute()
    target = Path(target).expanduser().absolute()
    ffmpeg = Path(ffmpeg).expanduser().absolute()
    models = Path(model_dir) if model_dir else model_store.model_directory()
    if not model_store.check(models):
        raise ValueError('Модель отсутствует или повреждена. Установите зависимости обработки через диагностику.')
    with wave.open(str(source), 'rb') as w:
        if w.getframerate() != 48000 or w.getnchannels() not in (1, 2) or w.getsampwidth() != 2 or not w.getnframes():
            raise ValueError('Сначала конвертируйте файл в 48 кГц, 16-bit mono/stereo WAV.')
    if not ffmpeg.is_file(): raise ValueError('FFmpeg недоступен')
    target.mkdir(parents=False, exist_ok=False)
    raw = target / 'временные файлы'; raw.mkdir()
    tools = raw / 'tools'; tools.mkdir()
    ffmpeg_link = tools / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
    try:
        os.link(ffmpeg, ffmpeg_link)
    except OSError:
        shutil.copy2(ffmpeg, ffmpeg_link)
    os.environ['PATH'] = str(tools) + os.pathsep + os.environ.get('PATH', '')
    os.environ.pop('AUDIO_SEPARATOR_MODEL_DIR', None)
    os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
    # All dependencies and assets are installed separately before this point.
    from audio_separator.separator import Separator
    separator = Separator(log_level=logging.INFO, model_file_dir=str(models), output_dir=str(raw),
                          output_format='WAV', sample_rate=44100, use_soundfile=True,
                          normalization_threshold=1.0,
                          mdx_params={'hop_length':1024, 'segment_size':256, 'overlap':0.25,
                                      'batch_size':1, 'enable_denoise':bool(denoise)})
    separator.load_model('UVR-MDX-NET-Inst_HQ_3.onnx')
    separator.separate(str(source), custom_output_names={'Vocals': 'vocals', 'Instrumental': 'instrumental'})
    output = {}
    for stem in ('vocals', 'instrumental'):
        input_path = raw / (stem + '.wav')
        if not input_path.is_file(): raise ValueError('Движок не создал ожидаемую дорожку: ' + stem)
        destination = target / (stem + '.wav')
        workspace, stage, args = prepare(input_path, destination, 2)
        try:
            subprocess.run([str(ffmpeg), *args], stdout=subprocess.DEVNULL, check=True)
            publish(stage, destination, 2)
        finally:
            workspace.cleanup()
        output[stem] = str(destination)
    shutil.rmtree(raw)
    return {'input':str(source), 'model':'UVR-MDX-NET-Inst_HQ_3.onnx',
            'model_sha256':model_store.ASSETS['UVR-MDX-NET-Inst_HQ_3.onnx'][1],
            'engine':'audio-separator 0.41.1', 'denoise':bool(denoise), 'outputs':output}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True); parser.add_argument('--output-dir', required=True)
    parser.add_argument('--ffmpeg', required=True); parser.add_argument('--denoise', action='store_true')
    args = parser.parse_args()
    try:
        result = separate(args.input, args.output_dir, args.ffmpeg, args.denoise)
        print(json.dumps(result, ensure_ascii=True), flush=True); return 0
    except Exception as exc:
        print(f'Ошибка обработки: {exc}', file=sys.stderr, flush=True); return 1


if __name__ == '__main__':
    sys.exit(main())
