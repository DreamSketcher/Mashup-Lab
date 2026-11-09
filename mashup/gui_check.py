"""Check GUI and actual FFmpeg executable in the current Python environment."""
import subprocess
import sys


def main():
    ok = True
    try:
        from PySide6.QtWidgets import QApplication  # noqa: F401
        print('PySide6: доступен.')
    except (ImportError, OSError) as exc:
        print(f'PySide6: недоступен: {exc}')
        ok = False
    try:
        from .conversion import ffmpeg_executable
        executable = ffmpeg_executable()
        result = subprocess.run([executable, '-version'], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=15, check=True)
        version = result.stdout.decode('utf-8', 'replace').splitlines()
        if not version or not version[0].startswith('ffmpeg version '):
            raise ValueError('исполняемый файл не сообщил версию FFmpeg')
        print(f'FFmpeg: доступен ({version[0]}); путь: {executable}')
    except Exception as exc:
        print(f'FFmpeg: недоступен: {exc}')
        ok = False
    if not ok:
        print('Для установки или восстановления выберите пункт 8 (либо пункт 2).')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
