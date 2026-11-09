"""Health checks for the isolated source-separation environment."""
import importlib.metadata as metadata
import subprocess
import sys


def main():
    if sys.argv[1:] not in (['check-python'], ['check']): return 2
    if sys.version_info[:2] != (3, 12):
        print('Движку требуется Python 3.12; найден ' + sys.version.split()[0]); return 1
    if sys.argv[1:] == ['check-python']:
        print('Python 3.12: OK'); return 0
    try:
        if metadata.version('audio-separator') != '0.41.1' or metadata.version('onnxruntime') != '1.31.1':
            raise ValueError('Неверная версия движка или ONNX Runtime')
        from audio_separator.separator import Separator  # noqa: F401
        from .model_store import check
        if not check(): raise ValueError('Модель или параметры отсутствуют либо повреждены')
        if subprocess.run([sys.executable, '-m', 'pip', 'check'], check=False).returncode:
            raise ValueError('pip check обнаружил проблемы')
        print('Движок UVR и модель: OK'); return 0
    except Exception as exc:
        print(f'Движок UVR: недоступен: {exc}'); return 1


if __name__ == '__main__':
    sys.exit(main())
