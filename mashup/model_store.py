"""Pinned UVR model assets; install explicitly, validate before inference."""
import hashlib
import os
from pathlib import Path
import tempfile
import urllib.request

REF = '3826b05b570dbd4fbedbc807758803b35348ba1b'
BASE = 'https://api.github.com/repos/TRvlvr/application_data/contents/'
ASSETS = {
    'UVR-MDX-NET-Inst_HQ_3.onnx': ('https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/UVR-MDX-NET-Inst_HQ_3.onnx', '317554b07fe1ea5279a77f2b1520a41ea4b93432560c4ffd08792c30fddf9adc', 66759214),
    'download_checks.json': (BASE + 'filelists/download_checks.json?ref=' + REF, 'd3622e1fa19c161d3cf704927711b453d593a3f1eb0f2e0838c3136907935151', 28267),
    'mdx_model_data.json': (BASE + 'mdx_model_data/model_data_new.json?ref=' + REF, '1aca8f9bcc57233bc714029663a9ec2345d9c7721f91e5e08f46392a879c6a9a', 15358),
    'vr_model_data.json': (BASE + 'vr_model_data/model_data_new.json?ref=' + REF, '6a2021b9aa355c10f845b68c73944d47bd9e1fdf37b8a584b14ce8f88b09bb2f', None),
}


def model_directory():
    return Path.home() / '.mashup-lab' / 'models' / 'uvr-mdx-hq3'


def valid(path, digest, size=None):
    try:
        if not path.is_file() or (size is not None and path.stat().st_size != size):
            return False
        h = hashlib.sha256()
        with path.open('rb') as src:
            for data in iter(lambda: src.read(1024*1024), b''):
                h.update(data)
        return h.hexdigest() == digest
    except OSError:
        return False


def check(directory=None):
    directory = Path(directory) if directory else model_directory()
    return all(valid(directory / name, sha, size) for name, (_, sha, size) in ASSETS.items())


def install(directory=None):
    directory = Path(directory) if directory else model_directory()
    directory.mkdir(parents=True, exist_ok=True)
    for name, (url, sha, size) in ASSETS.items():
        target = directory / name
        if valid(target, sha, size):
            print(f'{name}: OK', flush=True); continue
        print(f'Загрузка {name} ...', flush=True)
        request = urllib.request.Request(url, headers={'User-Agent': 'Mashup-Lab', 'Accept': 'application/vnd.github.raw+json'})
        fd, temp_name = tempfile.mkstemp(prefix='.download-', dir=directory)
        try:
            with os.fdopen(fd, 'wb') as dst, urllib.request.urlopen(request, timeout=90) as response:
                if not response.geturl().startswith('https://'):
                    raise ValueError('Небезопасное перенаправление')
                total = 0
                while True:
                    chunk = response.read(1024*1024)
                    if not chunk: break
                    total += len(chunk)
                    if total > (size if size is not None else 10*1024*1024):
                        raise ValueError('Слишком большой файл')
                    dst.write(chunk)
            if not valid(Path(temp_name), sha, size):
                raise ValueError(f'{name}: размер или SHA-256 не совпадают')
            # Replace only our own fixed cache asset, never source or output audio.
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name): os.unlink(temp_name)
    print(f'Модель и параметры проверены: {directory}', flush=True)


def main():
    import sys
    try:
        if sys.argv[1:] == ['install']:
            install(); return 0
        if sys.argv[1:] == ['check']:
            if check(): print(f'Модель доступна: {model_directory()}'); return 0
            print('Модель отсутствует или повреждена. Установите обработку в диагностике.'); return 1
        print('usage: python -m mashup.model_store install|check'); return 2
    except Exception as exc:
        print(f'Ошибка установки модели: {exc}', file=sys.stderr); return 1


if __name__ == '__main__':
    raise SystemExit(main())
