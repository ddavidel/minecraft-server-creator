"""Server detail: header, live console, resource stats and actions (US2)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from mcsc import MinecraftServer, ServerState

from mcsc_gui.config import settings as mcssettings
from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.config_files import config_file_label, visible_config_files
from mcsc_gui.ui.server_events import ServerEvents
from mcsc_gui.ui.tasks import run_task
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.usage import UsageHistory, usage_history
from mcsc_gui.ui.widgets.card import Card
from mcsc_gui.ui.widgets.common import button, icon_button, label
from mcsc_gui.ui.widgets.console import ConsoleView
from mcsc_gui.ui.widgets.stat_tile import StatTile
from mcsc_gui.ui.widgets.status_badge import StatusBadge
from mcsc_gui.core.os_utils import open_file_explorer

USAGE_INTERVAL_MS = 1000


class ServerDetailPage(QWidget):
    """Created on navigation, destroyed when left (see :meth:`dispose`)."""

    title_changed = Signal(str)
    edit_file_requested = Signal(str, str)  # server_id, filename
    edit_requested = Signal(str)  # server_id
    delete_requested = Signal(str)  # server_id

    def __init__(self, server: MinecraftServer, events: ServerEvents,
                 history: UsageHistory = usage_history, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")
        self.server = server
        self._events = events
        self._history = history
        self._disposed = False
        s = TOKENS.spacing

        root = QVBoxLayout(self)
        root.setContentsMargins(s.xxl, s.xl, s.xxl, s.xl)
        root.setSpacing(s.lg)

        # ----------------------------------------------------------- header
        header = QHBoxLayout()
        header.setSpacing(s.md)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        name_row = QHBoxLayout()
        name_row.setSpacing(s.sm)
        self.name_label = label("", "display")
        self.name_label.setTextFormat(Qt.TextFormat.PlainText)
        self.name_label.setToolTip(f"ID: {server.id}")
        name_row.addWidget(self.name_label)
        self.badge = StatusBadge(server.state)
        name_row.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignVCenter)
        name_row.addStretch(1)
        titles.addLayout(name_row)
        self.details_label = label("", "muted")
        titles.addWidget(self.details_label)
        header.addLayout(titles, 1)

        self.folder_button = icon_button("folder", _("Open server folder"))
        self.folder_button.clicked.connect(lambda: open_file_explorer(self.server.path))
        header.addWidget(self.folder_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.start_button = button(_("Start"), "play_arrow", variant="primary")
        self.stop_button = button(_("Stop"), "stop")
        self.start_button.clicked.connect(self._start)
        self.stop_button.clicked.connect(self._stop)
        header.addWidget(self.start_button, 0, Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.stop_button, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(header)

        # ------------------------------------------------------------- body
        body = QHBoxLayout()
        body.setSpacing(s.lg)
        self.console = ConsoleView(mcssettings.MAX_LOG_LINES)
        self.console.command_submitted.connect(self._send_command)
        body.addWidget(self.console, 1)

        side = QVBoxLayout()
        side.setSpacing(s.md)
        side_widget = QWidget()
        side_widget.setFixedWidth(320)
        side_widget.setLayout(side)
        side.setContentsMargins(0, 0, 0, 0)

        side.addWidget(label(_("RESOURCES"), "overline"))
        stats = QGridLayout()
        stats.setSpacing(s.sm)
        p = TOKENS.palette
        self.ram_tile = StatTile("donut_large", _("RAM usage"), "MB", p.accent)
        self.cpu_tile = StatTile("memory", _("CPU usage"), "%", p.info)
        self.read_tile = StatTile("disk_read", _("Disk read"), "MB/s", p.warning)
        self.write_tile = StatTile("disk_write", _("Disk write"), "MB/s", p.dirt)
        stats.addWidget(self.ram_tile, 0, 0)
        stats.addWidget(self.cpu_tile, 0, 1)
        stats.addWidget(self.read_tile, 1, 0)
        stats.addWidget(self.write_tile, 1, 1)
        side.addLayout(stats)

        side.addSpacing(s.sm)
        side.addWidget(label(_("SETTINGS"), "overline"))
        actions = Card(padding=s.sm)
        actions.layout_.setSpacing(2)
        self.edit_button = button(_("Edit server settings"), "tune", variant="ghost")
        self.edit_button.setStyleSheet("text-align: left;")
        self.edit_button.clicked.connect(lambda: self.edit_requested.emit(self.server.id))
        actions.layout_.addWidget(self.edit_button)
        self._files_layout = QVBoxLayout()
        self._files_layout.setSpacing(2)
        actions.layout_.addLayout(self._files_layout)
        self.delete_button = button(_("Delete server"), "delete", variant="ghost",
                                    icon_color=p.danger)
        self.delete_button.setProperty("tone", "danger")
        self.delete_button.setStyleSheet("text-align: left;")
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self.server.id))
        actions.layout_.addWidget(self.delete_button)
        side.addWidget(actions)
        side.addStretch(1)
        body.addWidget(side_widget)
        root.addLayout(body, 1)

        self.file_buttons: dict[str, QWidget] = {}

        # --------------------------------------------------------- wiring
        self.refresh()
        self.console.set_lines(list(server.output))
        events.output_lines.connect(self._on_output)
        events.state_changed.connect(self._on_state_changed)
        events.server_updated.connect(self._on_server_updated)

        self.usage_timer = QTimer(self)
        self.usage_timer.setInterval(USAGE_INTERVAL_MS)
        self.usage_timer.timeout.connect(self._sample_usage)
        self.usage_timer.start()
        self._sample_usage()

    # ------------------------------------------------------------- lifecycle

    def page_title(self) -> str:
        return self.server.name

    def dispose(self) -> None:
        """Disconnect from the app-wide signals (called before ``deleteLater``)."""
        if self._disposed:
            return
        self._disposed = True
        self.usage_timer.stop()
        for signal, slot in (
            (self._events.output_lines, self._on_output),
            (self._events.state_changed, self._on_state_changed),
            (self._events.server_updated, self._on_server_updated),
        ):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    # ---------------------------------------------------------------- state

    def refresh(self) -> None:
        server = self.server
        config = server.config
        self.name_label.setText(config.name)
        self.details_label.setText(
            f"{config.server_type.label} {config.version} · {config.ram_gb} GB RAM · "
            f"{_('Port')} {config.port}"
        )
        self.badge.set_state(server.state)
        self.start_button.setEnabled(sm.can_start(server))
        self.stop_button.setEnabled(sm.can_stop(server))
        self.console.set_input_enabled(server.is_active)
        self._refresh_files()

    def _refresh_files(self) -> None:
        files = visible_config_files(self.server)
        if [f for f, _e in files] != list(self.file_buttons):
            while self._files_layout.count():
                item = self._files_layout.takeAt(0)
                if item.widget() is not None:
                    item.widget().deleteLater()
            self.file_buttons = {}
            for filename, _enabled in files:
                btn = button(config_file_label(filename), "edit_note", variant="ghost",
                             tooltip=filename)
                btn.setStyleSheet("text-align: left;")
                btn.clicked.connect(
                    lambda _c=False, f=filename: self.edit_file_requested.emit(self.server.id, f)
                )
                self._files_layout.addWidget(btn)
                self.file_buttons[filename] = btn
        for filename, enabled in files:
            self.file_buttons[filename].setEnabled(enabled)

    def _on_output(self, server_id: str, lines: list) -> None:
        if server_id == self.server.id:
            self.console.append_lines(lines)

    def _on_state_changed(self, server_id: str, _old: str, new: str) -> None:
        if server_id != self.server.id:
            return
        if new == ServerState.STARTING:
            self.console.set_lines([])  # pymcsc clears its buffer on start
            self._history.reset(server_id)
        elif new == ServerState.STOPPED:
            self._history.reset(server_id)
            self._sample_usage()
        self.refresh()

    def _on_server_updated(self, server_id: str) -> None:
        if server_id == self.server.id:
            self.refresh()
            self.title_changed.emit(self.server.name)

    def _sample_usage(self) -> None:
        usage = self._history.sample(self.server)
        active = self.server.is_active
        sid = self.server.id
        h = self._history
        self.ram_tile.set_value(usage.ram_mb if active else None, h.series(sid, "ram_mb"))
        self.cpu_tile.set_value(usage.cpu_percent if active else None,
                                h.series(sid, "cpu_percent"))
        self.read_tile.set_value(usage.disk_read_mb if active else None,
                                 h.series(sid, "disk_read_mb"))
        self.write_tile.set_value(usage.disk_write_mb if active else None,
                                  h.series(sid, "disk_write_mb"))

    # -------------------------------------------------------------- actions

    def _start(self) -> None:
        run_task(sm.start_server(self.server), disable=[self.start_button],
                 on_success=lambda _r: self.refresh())

    def _stop(self) -> None:
        run_task(sm.stop_server(self.server), disable=[self.stop_button],
                 on_success=lambda _r: self.refresh())

    def _send_command(self, command: str) -> None:
        # "stop" is routed to stop_server (graceful, with SERVER_STOP_TIMEOUT)
        run_task(sm.send_command(self.server, command))
