"""Small JSON files in the data directory, written atomically and private to the owner."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any


class JsonFile:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> dict[str, Any]:
        with self._lock:
            try:
                value = json.loads(self.path.read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                return {}
            return value if isinstance(value, dict) else {}

    def save(self, value: dict[str, Any]) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(value, f, indent=2)
            os.replace(tmp, self.path)

    def update(self, **changes: Any) -> dict[str, Any]:
        value = self.load()
        value.update(changes)
        self.save(value)
        return value


class Store:
    """Everything the app persists.

    - ``secrets.json``: Zwift email, password and tokens.
    - ``state.json``: settings, last sync status and history (no credentials).
    - ``garmin/``: Garmin login tokens, managed by the garminconnect library.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(data_dir, 0o700)
        self.garmin_dir = data_dir / "garmin"
        self.secrets = JsonFile(data_dir / "secrets.json")
        self.state = JsonFile(data_dir / "state.json")
