"""
Qt adapter for pymcsc listeners.

pymcsc calls its listeners in the asyncio bridge thread. :class:`ServerEvents`
registers **one** state/output listener per server and turns them into Qt
signals delivered in the UI thread (the object lives there, so emitting from
another thread is a queued connection). Views subscribe to the signals and
filter by server id; a view going away never touches the pymcsc listeners.

Console output is batched: lines are buffered per server (under a lock) and a
UI-thread timer emits them as one ``output_lines`` signal at most every
``flush_interval_ms``.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from mcsc import MinecraftServer, ServerState

from mcsc_gui.core import server_manager as sm

logger = logging.getLogger(__name__)

FLUSH_INTERVAL_MS = 50


class ServerEvents(QObject):
    """One per app. Signals are emitted in the UI thread."""

    state_changed = Signal(str, str, str)  # server_id, old_state, new_state
    output_lines = Signal(str, list)  # server_id, [lines] (batch)
    server_added = Signal(str)  # server_id
    server_removed = Signal(str)  # server_id
    server_updated = Signal(str)  # server_id (name / RAM / version changed)
    busy_changed = Signal(str)  # server_id (backup, restore, export... started or ended)
    backups_changed = Signal(str)  # server_id (backup created or deleted)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        flush_interval_ms: int = FLUSH_INTERVAL_MS,
        track_registry: bool = True,
    ) -> None:
        super().__init__(parent)
        self._lock = threading.Lock()
        self._buffers: dict[str, list[str]] = {}
        self._listeners: dict[str, tuple[MinecraftServer, Callable[..., Any], Callable[..., Any]]] = {}
        self._track_registry = track_registry

        self._timer = QTimer(self)
        self._timer.setInterval(flush_interval_ms)
        self._timer.timeout.connect(self.flush)
        self._timer.start()

        if track_registry:
            sm.on_server_added(self._on_server_added)
            sm.on_server_removed(self._on_server_removed)
            sm.on_server_updated(self._on_server_updated)
            sm.on_server_busy_changed(self._on_busy_changed)
            sm.on_backups_changed(self._on_backups_changed)

    # ------------------------------------------------------------ listeners

    def attach(self, server: MinecraftServer) -> None:
        """Register the state/output listeners once per server. Thread-safe."""
        server_id = server.id

        def on_state(_server: MinecraftServer, old: ServerState, new: ServerState) -> None:
            self.state_changed.emit(server_id, str(old), str(new))

        def on_output(_server: MinecraftServer, line: str) -> None:
            with self._lock:
                self._buffers.setdefault(server_id, []).append(line)

        with self._lock:
            if server_id in self._listeners:
                return
            self._listeners[server_id] = (server, on_state, on_output)
        server.add_state_listener(on_state)
        server.add_output_listener(on_output)

    def attach_all(self, servers: Iterable[MinecraftServer]) -> None:
        for server in servers:
            self.attach(server)

    def detach(self, server: MinecraftServer | str) -> None:
        """Remove the listeners of a server. Thread-safe, no-op if not attached."""
        server_id = server if isinstance(server, str) else server.id
        with self._lock:
            entry = self._listeners.pop(server_id, None)
            self._buffers.pop(server_id, None)
        if entry is None:
            return
        attached, on_state, on_output = entry
        for remove, listener in (
            (attached.remove_state_listener, on_state),
            (attached.remove_output_listener, on_output),
        ):
            try:
                remove(listener)
            except ValueError:
                pass

    def is_attached(self, server_id: str) -> bool:
        with self._lock:
            return server_id in self._listeners

    def close(self) -> None:
        """Detach every server and stop tracking the registry."""
        self._timer.stop()
        with self._lock:
            ids = list(self._listeners)
        for server_id in ids:
            self.detach(server_id)
        if self._track_registry:
            sm.remove_callback(self._on_server_added)
            sm.remove_callback(self._on_server_removed)
            sm.remove_callback(self._on_server_updated)
            sm.remove_callback(self._on_busy_changed)
            sm.remove_callback(self._on_backups_changed)

    # --------------------------------------------------------------- output

    @Slot()
    def flush(self) -> None:
        """Emit the buffered output lines (UI thread)."""
        with self._lock:
            if not any(self._buffers.values()):
                return
            buffers, self._buffers = self._buffers, {}
        for server_id, lines in buffers.items():
            if lines:
                self.output_lines.emit(server_id, lines)

    # ------------------------------------------------- registry (any thread)

    def _on_server_added(self, server: MinecraftServer) -> None:
        self.attach(server)
        self.server_added.emit(server.id)

    def _on_server_removed(self, server: MinecraftServer) -> None:
        self.detach(server)
        self.server_removed.emit(server.id)

    def _on_server_updated(self, server: MinecraftServer) -> None:
        self.server_updated.emit(server.id)

    def _on_busy_changed(self, server: MinecraftServer) -> None:
        self.busy_changed.emit(server.id)

    def _on_backups_changed(self, server: MinecraftServer) -> None:
        self.backups_changed.emit(server.id)
