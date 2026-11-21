"""Recent resource usage samples per server, for the detail page sparklines."""

from __future__ import annotations

from collections import deque

from mcsc import MinecraftServer, ResourceUsage

HISTORY_SIZE = 60


class UsageHistory:
    """Keeps the last :data:`HISTORY_SIZE` samples of each server (UI thread only)."""

    def __init__(self, size: int = HISTORY_SIZE) -> None:
        self._size = size
        self._samples: dict[str, deque[ResourceUsage]] = {}
        self._players: dict[str, deque[float]] = {}

    def sample(self, server: MinecraftServer, players: int | None = None) -> ResourceUsage:
        """Read ``server.monitor.usage`` and store it (only while the server is active).

        ``players`` (online count, ``None`` = unknown) is stored with it, for the
        Players tile sparkline.
        """
        usage = server.monitor.usage
        if server.is_active:
            self._samples.setdefault(server.id, deque(maxlen=self._size)).append(usage)
            self._players.setdefault(server.id, deque(maxlen=self._size)).append(
                float(players or 0))
        return usage

    def get(self, server_id: str) -> list[ResourceUsage]:
        return list(self._samples.get(server_id, ()))

    def series(self, server_id: str, field: str) -> list[float]:
        if field == "players":
            return list(self._players.get(server_id, ()))
        return [getattr(u, field) for u in self._samples.get(server_id, ())]

    def reset(self, server_id: str) -> None:
        self._samples.pop(server_id, None)
        self._players.pop(server_id, None)


usage_history = UsageHistory()
