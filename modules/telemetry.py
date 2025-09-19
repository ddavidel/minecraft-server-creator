"""Telemetry"""

import os
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from appdirs import user_data_dir

import requests


DATA_DIR_PATH = user_data_dir("mcsc")
TELEMETRY_DIR_PATH = os.path.join(DATA_DIR_PATH, "telemetry")
TELEMETRY_API = "https://mcscreator.altervista.org/telemetry/receiver.php"


ALLOWED_EVENTS = [
    "app_start",
    "app_close",
    "server_create",
    "server_delete",
    "server_start",
    "server_stop",
    "settings_change",
]

class TelemetryClient:
    """Telemetry client
    Communicates with telemetry server sending info
    """

    def __init__(
        self, server_url: str = TELEMETRY_API, storage_dir: Path = TELEMETRY_DIR_PATH
    ):
        self.server_url = server_url.rstrip("/")
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Generate uuid
        self.uuid_file = self.storage_dir / "client.conf"
        if self.uuid_file.exists():
            self.client_uuid = self.uuid_file.read_text().strip()
        else:
            self.client_uuid = str(uuid.uuid4())
            self.uuid_file.write_text(self.client_uuid)

        self.flush_pending()

    def _save_pending(self, payload: dict):
        """Save payload on a file to be sent once server is available"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        pending_file = self.storage_dir / f"pending_{timestamp}.json"
        with open(pending_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def _load_pending(self):
        """Load pending payload(s)"""
        return sorted(self.storage_dir.glob("pending_*.json"))

    def _send(self, payload: dict) -> bool:
        """Try sending payload to telemetry server
        Args:
            payload (dict): the payload

        Returns:
            True if sent else False"""
        try:
            r = requests.post(self.server_url, json=payload, timeout=5)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def send_event(self, event_name: str, details: dict = None):
        """Send an event (or save it locally if server does not answer)"""
        # Assert parameters are valid
        assert isinstance(event_name, str), "'event_name' is not a string"
        if details is not None:
            assert isinstance(details, dict), "Invalid 'details' dict"
        assert event_name in ALLOWED_EVENTS, "'event_name' not allowed"

        payload = {
            "client_id": self.client_uuid,
            "event_name": event_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details or {},
        }

        if not self._send(payload):
            # If failed save to pending
            payload["details"]["delayed"] = True
            self._save_pending(payload)

    def flush_pending(self):
        """Retry sending pending payload(s)"""
        for file in self._load_pending():
            try:
                with open(file, "r", encoding="utf-8") as f:
                    payload = json.load(f)

                if self._send(payload):
                    file.unlink()  # delete if sent
            except Exception:  # pylint: disable=broad-exception-caught
                pass
