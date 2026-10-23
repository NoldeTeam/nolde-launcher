"""Versioned JSON persistence with atomic writes and corrupt-file recovery."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable


class JsonStore:
    """Stores one JSON document. Writes go to a temp file that is fsynced and
    then atomically moved into place, so a crash mid-write cannot leave a
    half-written settings or library file behind."""

    def __init__(self, path: Path, schema_version: int,
                 default_factory: Callable[[], dict[str, Any]]) -> None:
        self.path = Path(path)
        self.schema_version = schema_version
        self._default_factory = default_factory
        self._lock = threading.Lock()

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._default_factory()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            self._quarantine_corrupt_file()
            return self._default_factory()
        if not isinstance(data, dict) or data.get("schema_version") != self.schema_version:
            # Unknown or older schema: keep the file for inspection, start fresh.
            self._quarantine_corrupt_file()
            return self._default_factory()
        return data

    def save(self, data: dict[str, Any]) -> None:
        payload = dict(data)
        payload["schema_version"] = self.schema_version
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        with self._lock:
            with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)

    def _quarantine_corrupt_file(self) -> None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = self.path.with_name(f"{self.path.name}.corrupt-{stamp}")
        try:
            os.replace(self.path, backup)
        except OSError:
            pass
