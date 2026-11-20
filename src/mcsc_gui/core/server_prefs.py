"""
Per-server app preferences, stored by the app (not in the pymcsc registry).

They are app policy, not server data: today only the automatic backup override
(``auto_backup``: ``default``, ``never``, ``on_start`` or ``on_stop``). Stored as
JSON keyed by server id and removed when a server is deleted.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ServerPrefs:
    """A small JSON store ``{server_id: {key: value}}``. Thread-safe."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] | None = None

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._data is None:
            try:
                with open(self.path, encoding="utf-8") as file:
                    data = json.load(file)
                self._data = {str(k): dict(v) for k, v in data.items() if isinstance(v, dict)}
            except FileNotFoundError:
                self._data = {}
            except (OSError, ValueError, AttributeError) as e:
                logger.warning(f"Can't read server preferences {self.path}: {e}")
                self._data = {}
        return self._data

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as file:
            json.dump(self._data or {}, file, indent=4)
        os.replace(tmp, self.path)

    def get(self, server_id: str, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._load().get(server_id, {}).get(key, default)

    def set(self, server_id: str, key: str, value: Any) -> None:
        """Set a preference (``None`` removes it) and save."""
        with self._lock:
            data = self._load()
            prefs = data.setdefault(server_id, {})
            if value is None:
                prefs.pop(key, None)
            else:
                prefs[key] = value
            if not prefs:
                data.pop(server_id, None)
            self._save()

    def remove(self, server_id: str) -> None:
        """Forget every preference of a server."""
        with self._lock:
            if self._load().pop(server_id, None) is not None:
                self._save()
