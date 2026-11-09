"""Best-effort, local per-session JSONL diagnostics. No audio data recorded."""
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid


class SessionTrace:
    def __init__(self, directory=None):
        self.path = None
        self.error = None
        directory = Path(directory) if directory else Path.home() / '.mashup-lab' / 'traces'
        try:
            directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            self.path = directory / f'session-{stamp}-{uuid.uuid4().hex[:8]}.jsonl'
            with self.path.open('x', encoding='utf-8'):
                pass
        except OSError as exc:
            self.error = str(exc)

    def emit(self, event, **data):
        entry = {'time_utc': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
                 'event': event, **data}
        if self.path is not None and self.error is None:
            try:
                with self.path.open('a', encoding='utf-8') as out:
                    out.write(json.dumps(entry, ensure_ascii=True, default=str) + '\n')
            except OSError as exc:
                self.error = str(exc)
        return entry
