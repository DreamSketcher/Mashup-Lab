"""Explicit, external FFmpeg file preparation; not renderer SRC.

The output must be a new file. Only the first audio stream is used. Input and
output are local paths; no shell or network protocol is used.
"""
import os
from pathlib import Path
import shutil
import tempfile
import wave

from .model import ProjectError


def ffmpeg_executable():
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise ProjectError('FFmpeg не установлен: установите requirements-gui.txt или выберите пункт 8 лаунчера.') from exc
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (RuntimeError, OSError) as exc:
        raise ProjectError(f'FFmpeg недоступен: {exc}') from exc


def prepare(source, destination, channels):
    source = Path(source).expanduser().absolute()
    destination = Path(destination).expanduser().absolute()
    if not source.is_file():
        raise ProjectError('Входной файл не найден или не является файлом.')
    if destination.suffix.lower() != '.wav':
        raise ProjectError('Выходной файл должен иметь расширение .wav.')
    if not destination.parent.is_dir():
        raise ProjectError('Родительская папка выходного файла не существует.')
    if destination.exists() or destination.is_symlink():
        raise ProjectError('Выходной файл уже существует; выберите новое имя.')
    if channels not in (1, 2):
        raise ProjectError('Число каналов должно быть 1 или 2.')
    try:
        workspace = tempfile.TemporaryDirectory(prefix='.mashup-convert-', dir=str(destination.parent))
    except OSError as exc:
        raise ProjectError(f'Не удалось создать временную папку: {exc}') from exc
    temp_output = Path(workspace.name) / 'audio.wav'
    arguments = ['-nostdin', '-n', '-loglevel', 'info', '-protocol_whitelist', 'file,pipe',
                 '-i', str(source), '-map', '0:a:0', '-vn', '-map_metadata', '-1',
                 '-ar', '48000', '-ac', str(channels), '-c:a', 'pcm_s16le',
                 '-f', 'wav', '-progress', 'pipe:1', str(temp_output)]
    return workspace, temp_output, arguments


def publish(temp_output, destination, channels):
    """Check renderer-compatible PCM and publish without replacing any file."""
    try:
        with wave.open(str(temp_output), 'rb') as wav:
            info = {'sample_rate': wav.getframerate(), 'channels': wav.getnchannels(),
                    'frames': wav.getnframes(), 'bits': wav.getsampwidth() * 8}
            if (info['sample_rate'] != 48000 or info['channels'] != channels or
                    info['bits'] != 16 or info['frames'] < 1 or wav.getcomptype() != 'NONE'):
                raise ProjectError('FFmpeg создал WAV в неподдерживаемом формате.')
            remaining = info['frames']
            while remaining:
                n = min(remaining, 65536)
                if len(wav.readframes(n)) != n * channels * 2:
                    raise ProjectError('Сконвертированный WAV неполный.')
                remaining -= n
        # Hardlink is an atomic no-replace publish on supported filesystems.
        # An exclusive copy is a fallback for filesystems without hardlinks;
        # if that copy is interrupted, its partial output remains for inspection.
        try:
            os.link(temp_output, destination)
        except FileExistsError as exc:
            raise ProjectError('Выходной файл уже существует; выберите новое имя.') from exc
        except OSError:
            with Path(temp_output).open('rb') as src, Path(destination).open('xb') as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
        return info
    except (OSError, wave.Error, EOFError) as exc:
        raise ProjectError(f'Не удалось проверить или сохранить WAV: {exc}. При прерывании копирования может остаться неполный файл.') from exc
