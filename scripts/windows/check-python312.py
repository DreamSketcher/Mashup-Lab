"""Validate the private CPython runtime before creating an environment."""
import struct
import sys

if sys.version_info[:3] != (3, 12, 10) or struct.calcsize('P') != 8:
    print('Требуется локальный CPython 3.12.10 x64; найден', sys.version)
    sys.exit(1)

import ensurepip  # noqa: F401
import venv  # noqa: F401
print('Локальный Python 3.12.10 x64: OK')
