"""Resource-bounded JSON reading for untrusted manifest and policy inputs."""
import json

MAX_BYTES = 1_048_576
MAX_DEPTH = 32
MAX_STRING_LENGTH = 4096


class SafeJSONError(ValueError):
    pass


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise SafeJSONError(f'duplicate JSON key: {key[:80]}')
        out[key] = value
    return out


def _constant(value):
    raise SafeJSONError(f'invalid JSON constant: {value}')


def decode(data):
    if not isinstance(data, bytes):
        raise TypeError('JSON input must be bytes')
    if len(data) > MAX_BYTES:
        raise SafeJSONError('JSON exceeds byte limit')
    try:
        text = data.decode('utf-8', 'strict')
        # Bound nesting before json.loads. Brackets inside strings and escaped
        # quotes do not affect depth. JSON validity remains the decoder's job.
        depth = 0
        in_string = False
        escaped = False
        for char in text:
            if in_string:
                if escaped:
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char in '[{':
                depth += 1
                if depth > MAX_DEPTH:
                    raise SafeJSONError('JSON exceeds nesting limit')
            elif char in ']}':
                depth -= 1
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
        stack = [value]
        while stack:
            item = stack.pop()
            if isinstance(item, str):
                if len(item) > MAX_STRING_LENGTH:
                    raise SafeJSONError('JSON string exceeds length limit')
            elif isinstance(item, dict):
                stack.extend(item.keys())
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
        return value
    except SafeJSONError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise SafeJSONError(f'invalid JSON: {exc}') from exc


def read_bounded(path):
    # Read at most limit + 1 even if the file grows after opening/stat.
    with open(path, 'rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise SafeJSONError('JSON exceeds byte limit')
    return data
