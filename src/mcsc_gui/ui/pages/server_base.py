"""
Base of the server pages (overview, console, configuration, backups, settings).

Every section has the same header (name, state, folder, Start/Stop) and listens
to the app-wide :class:`ServerEvents` for its server only. Pages are created on
navigation and destroyed when left: :meth:`ServerPage.dispose` disconnects them.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from mcsc import MinecraftServer

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.os_utils import open_file_explorer
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.navigator import BACKUPS, CONFIGURATION, CONSOLE, SERVER, SERVER_SETTINGS
from mcsc_gui.ui.server_events import ServerEvents
from mcsc_gui.ui.tasks import run_task
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.common import button, icon_button, label
from mcsc_gui.ui.widgets.status_badge import StatusBadge

SECTION_TITLES: dict[str, str] = {
    SERVER: "Overview",
    CONSOLE: "Console",
    CONFIGURATION: "Configuration",
    BACKUPS: "Backups",
    SERVER_SETTINGS: "Settings",
}


class ServerHeader(QWidget):
    """Name, state, "open folder" and Start/Stop of a server."""

    def __init__(self, server: MinecraftServer, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.server = server
        s = TOKENS.spacing
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(s.md)

        name_row = QHBoxLayout()
        name_row.setSpacing(s.sm)
        self.name_label = label("", "display")
        self.name_label.setTextFormat(Qt.TextFormat.PlainText)
        self.name_label.setToolTip(f"ID: {server.id}")
        name_row.addWidget(self.name_label)
        self.badge = StatusBadge(server.state)
        name_row.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignVCenter)
        name_row.addStretch(1)
        row.addLayout(name_row, 1)

        self.folder_button = icon_button("folder", _("Open server folder"))
        self.folder_button.clicked.connect(lambda: open_file_explorer(self.server.path))
        row.addWidget(self.folder_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.start_button = button(_("Start"), "play_arrow", variant="primary")
        self.stop_button = button(_("Stop"), "stop")
        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.stop)
        row.addWidget(self.start_button, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.stop_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.refresh()

    def refresh(self) -> None:
        server = self.server
        config = server.config
        self.name_label.setText(config.name)
        self.badge.set_state(server.state)
        self.badge.set_activity(sm.activity_label(server))
        self.start_button.setEnabled(sm.can_start(server))
        self.stop_button.setEnabled(sm.can_stop(server))

    def start(self) -> None:
        run_task(sm.start_server(self.server), disable=[self.start_button],
                 on_success=lambda _r: self.refresh())

    def stop(self) -> None:
        run_task(sm.stop_server(self.server), disable=[self.stop_button],
                 on_success=lambda _r: self.refresh())


class ServerPage(QWidget):
    """A section of a server. Subclasses fill :attr:`body` and override the ``on_*`` hooks."""

    section = SERVER

    title_changed = Signal(str)
    section_requested = Signal(str, str)  # server_id, section
    edit_file_requested = Signal(str, str)  # server_id, filename
    delete_requested = Signal(str)  # server_id
    clone_requested = Signal(str)  # server_id

    def __init__(self, server: MinecraftServer, events: ServerEvents,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")
        self.server = server
        self._events = events
        self._disposed = False
        self._connections: list[tuple[object, object]] = []
        s = TOKENS.spacing

        root = QVBoxLayout(self)
        root.setContentsMargins(s.xxl, s.xl, s.xxl, s.xl)
        root.setSpacing(s.lg)
        self.header = ServerHeader(server)
        root.addWidget(self.header)
        self.body = QVBoxLayout()
        self.body.setSpacing(s.lg)
        root.addLayout(self.body, 1)

        self._listen(events.state_changed, self._on_state_changed)
        self._listen(events.server_updated, self._on_server_updated)
        self._listen(events.busy_changed, self._on_busy_changed)
        self._listen(events.backups_changed, self._on_backups_changed)
        self._listen(events.output_lines, self._on_output)
        self._listen(events.players_changed, self._on_players_changed)

    # ------------------------------------------------------------- lifecycle

    def page_title(self) -> str:
        if self.section == SERVER:
            return self.server.name
        return f"{self.server.name} · {_(SECTION_TITLES[self.section])}"

    def _listen(self, signal, slot) -> None:
        signal.connect(slot)
        self._connections.append((signal, slot))

    def dispose(self) -> None:
        """Disconnect from the app-wide signals (called before ``deleteLater``)."""
        if self._disposed:
            return
        self._disposed = True
        for signal, slot in self._connections:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._connections.clear()
        self.on_dispose()

    def go_to(self, section: str) -> None:
        self.section_requested.emit(self.server.id, section)

    # ----------------------------------------------------------------- hooks

    def refresh(self) -> None:
        """Re-read the server (state, busy, settings). Subclasses extend it."""
        self.header.refresh()

    def on_state_changed(self, old: str, new: str) -> None:
        """The server's state changed (``refresh`` is called right after)."""

    def on_output(self, lines: list) -> None:
        """New console lines of the server."""

    def on_backups_changed(self) -> None:
        """A backup of the server was created or deleted."""

    def on_players_changed(self, status) -> None:
        """New online players status of the server (:class:`players.PlayerStatus`)."""

    def on_dispose(self) -> None:
        """Release timers and other resources."""

    # ---------------------------------------------------------------- events

    def _on_state_changed(self, server_id: str, old: str, new: str) -> None:
        if server_id == self.server.id:
            self.on_state_changed(old, new)
            self.refresh()

    def _on_server_updated(self, server_id: str) -> None:
        if server_id == self.server.id:
            self.refresh()
            self.title_changed.emit(self.page_title())

    def _on_busy_changed(self, server_id: str) -> None:
        if server_id == self.server.id:
            self.refresh()

    def _on_backups_changed(self, server_id: str) -> None:
        if server_id == self.server.id:
            self.on_backups_changed()

    def _on_output(self, server_id: str, lines: list) -> None:
        if server_id == self.server.id:
            self.on_output(lines)

    def _on_players_changed(self, server_id: str, status) -> None:
        if server_id == self.server.id:
            self.on_players_changed(status)
