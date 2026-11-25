"""Telemetry client with local fallback for offline use."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from functools import cache
from pathlib import Path
from typing import Any

import requests

from mcsc_gui.config.settings import TELEMETRY_API, TELEMETRY_DIR_PATH

ALLOWED_EVENTS = {
    "app_start",
    "app_close",
    "server_create",
    "server_delete",
    "server_start",
    "server_stop",
    "settings_change",
}


class TelemetryClient:
    """Telemetry client that stores pending events when the server is unavailable."""

    def __init__(
        self,
        server_url: str = TELEMETRY_API,
        storage_dir: str | Path = TELEMETRY_DIR_PATH,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.uuid_file = self.storage_dir / "client.conf"
        if self.uuid_file.exists():
            self.client_uuid = self.uuid_file.read_text(encoding="utf-8").strip()
        else:
            self.client_uuid = str(uuid.uuid4())
            self.uuid_file.write_text(self.client_uuid, encoding="utf-8")

        self.flush_pending()

    def _save_pending(self, payload: dict[str, Any]) -> Path:
        """Write a payload to disk so it can be retried later. Returns its file."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        pending_file = self.storage_dir / f"pending_{timestamp}.json"
        with pending_file.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        return pending_file

    def _load_pending(self) -> list[Path]:
        """Return queued telemetry payloads."""
        return sorted(self.storage_dir.glob("pending_*.json"))

    def _send(self, payload: dict[str, Any], timeout: float = 5) -> bool:
        """Send a payload and return whether it succeeded."""
        try:
            response = requests.post(self.server_url, json=payload, timeout=timeout)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def _payload(self, event_name: str, details: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(event_name, str):
            raise TypeError("'event_name' is not a string")
        if details is not None and not isinstance(details, dict):
            raise TypeError("Invalid 'details' dict")
        if event_name not in ALLOWED_EVENTS:
            raise ValueError("'event_name' not allowed")
        return {
            "client_id": self.client_uuid,
            "event_name": event_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": dict(details or {}),
        }

    @staticmethod
    def _delayed(payload: dict[str, Any]) -> dict[str, Any]:
        """Copy of ``payload`` marked as sent later than it happened."""
        return {**payload, "details": {**payload["details"], "delayed": True}}

    def send_event(self, event_name: str, details: dict[str, Any] | None = None) -> None:
        """Send an event, or queue it locally when telemetry is unavailable."""
        payload = self._payload(event_name, details)
        if not self._send(payload):
            self._save_pending(self._delayed(payload))

    def send_event_durable(self, event_name: str, details: dict[str, Any] | None = None,
                           timeout: float = 2) -> None:
        """Queue the event on disk first, then try to send it.

        For events sent while the process may be killed at any moment (the OS
        shutting down): if the send doesn't complete, the queued copy is sent
        at the next start by :meth:`flush_pending`.
        """
        payload = self._payload(event_name, details)
        pending_file = self._save_pending(self._delayed(payload))
        if self._send(payload, timeout=timeout):
            pending_file.unlink(missing_ok=True)

    def flush_pending(self) -> None:
        """Retry all pending payloads and delete those that are successfully sent."""
        for file in self._load_pending():
            try:
                with file.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                if self._send(payload):
                    file.unlink(missing_ok=True)
            except Exception:  # pragma: no cover - best effort retry logic
                continue


@cache
def get_telemetry_client() -> TelemetryClient:
    """Shared telemetry client, created on first use."""
    return TelemetryClient()


async def send_event_async(event_name: str, details: dict[str, Any] | None = None) -> None:
    """Send an event from a worker thread, so the event loop (and the UI) never blocks."""
    await asyncio.to_thread(get_telemetry_client().send_event, event_name, details)
