"""Check declared GUI requirements and runtime capabilities without installing anything.

Requirements (including -r files and markers) are the source of installed
package/version checks. Add runtime probes below when a dependency needs more
than its installed package metadata to be usable.
"""
from importlib import metadata
import json
from urllib.parse import urldefrag, parse_qs
from pathlib import Path
import subprocess
import sys


def declared_requirements(path, seen=None):
    from pip._vendor.packaging.requirements import Requirement
    seen = set() if seen is None else seen
    path = Path(path).resolve()
    if path in seen:
        raise ValueError(f'циклическое включение: {path}')
    seen.add(path)
    try:
        for raw in path.read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if line.startswith('#'):
                continue
            line = line.split(' #', 1)[0].strip()
            if not line:
                continue
            if line.startswith('-r '):
                yield from declared_requirements(path.parent / line[3:].strip(), seen)
            elif line.startswith('-'):
                raise ValueError(f'неподдерживаемая директива requirements: {line}')
            else:
                req = Requirement(line)
                if req.extras:
                    raise ValueError(f'неподдерживаемое требование: {line}')
                if not req.marker or req.marker.evaluate():
                    yield req
    finally:
        seen.remove(path)


def check_requirements(path):
    ok = True
    for req in declared_requirements(path):
        try:
            version = metadata.version(req.name)
        except metadata.PackageNotFoundError:
            print(f'{req.name}: не установлен ({req})')
            ok = False
            continue
        if req.url:
            expected_url, fragment = urldefrag(req.url)
            hashes = parse_qs(fragment)
            try:
                installed = json.loads(metadata.distribution(req.name).read_text('direct_url.json') or '{}')
                actual_hash = installed.get('archive_info', {}).get('hashes', {}).get('sha256')
                if installed.get('url') != expected_url or not hashes.get('sha256') or actual_hash != hashes['sha256'][0]:
                    raise ValueError('не совпадает URL или SHA-256 установленного архива')
            except (metadata.PackageNotFoundError, ValueError, TypeError) as exc:
                print(f'{req.name}: не подтверждён источник: {exc}')
                ok = False
                continue
        if req.specifier and not req.specifier.contains(version, prereleases=True):
            print(f'{req.name}: версия {version} не соответствует {req.specifier}')
            ok = False
        else:
            print(f'{req.name}: {version} — OK')
    return ok


def probe_imports():
    from PySide6.QtWidgets import QApplication  # noqa: F401
    import yaml, numpy, soundfile, librosa, music_key_detector  # noqa: F401
    from . import render  # noqa: F401
    return 'Импорт приложения и библиотек выполнен'


def probe_ffmpeg():
    import imageio_ffmpeg
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run([exe, '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=15, check=True)
    lines = result.stdout.decode('utf-8', 'replace').splitlines()
    if not lines or not lines[0].startswith('ffmpeg version '):
        raise ValueError('исполняемый файл не сообщил версию FFmpeg')
    return f'{lines[0]}; путь: {exe}'


# Add capability probes here for future non-package/native requirements.
PROBES = [('Импорты', probe_imports), ('FFmpeg', probe_ffmpeg)]


def main():
    ok = True
    requirements = Path(__file__).resolve().parent.parent / 'requirements-gui.txt'
    try:
        ok = check_requirements(requirements) and ok
    except Exception as exc:
        print(f'Не удалось проверить requirements: {exc}')
        ok = False
    try:
        result = subprocess.run([sys.executable, '-m', 'pip', 'check'], timeout=60, check=False)
        if result.returncode:
            ok = False
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f'pip check: ошибка: {exc}')
        ok = False
    for name, probe in PROBES:
        try:
            print(f'{name}: {probe()}')
        except Exception as exc:
            print(f'{name}: недоступен: {exc}')
            ok = False
    if not ok:
        print('Проверка не пройдена. Откройте Mashup-Lab.bat и выберите пункт 2 или 8.')
    else:
        print('Все проверенные зависимости и возможности доступны.')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
