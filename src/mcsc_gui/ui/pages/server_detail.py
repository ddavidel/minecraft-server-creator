"""Server detail: header, live console, resource stats, actions and backups (US2)."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mcsc import Backup, MinecraftServer, ServerState

from mcsc_gui.config import settings as mcssettings
from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.config_files import config_file_label, visible_config_files
from mcsc_gui.ui.dialogs.restore_backup import DeleteBackupDialog, RestoreBackupDialog
from mcsc_gui.ui.server_events import ServerEvents
from mcsc_gui.ui.tasks import FileProgress, run_blocking, run_task
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.usage import UsageHistory, usage_history
from mcsc_gui.ui.widgets.backup_list import BackupList
from mcsc_gui.ui.widgets.card import Card
from mcsc_gui.ui.widgets.common import button, icon_button, label
from mcsc_gui.ui.widgets.console import ConsoleView
from mcsc_gui.ui.widgets.stat_tile import StatTile
from mcsc_gui.ui.widgets.status_badge import StatusBadge
from mcsc_gui.core.os_utils import open_file_explorer

USAGE_INTERVAL_MS = 1000
SIDE_WIDTH = 320
_UNSAFE_FILE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def pick_export_path(parent: QWidget, server: MinecraftServer) -> str | None:
    """Native save dialog (it asks before overwriting an existing file)."""
    safe = _UNSAFE_FILE_CHARS.sub("_", server.name).strip(" .") or "server"
    path, _filter = QFileDialog.getSaveFileName(
        parent, _("Export server"), str(Path.home() / f"{safe}.zip"),
        _("MCSC export") + " (*.zip)",
    )
    if not path:
        return None
    return path if path.lower().endswith(".zip") else path + ".zip"


class ServerDetailPage(QWidget):
    """Created on navigation, destroyed when left (see :meth:`dispose`)."""

    title_changed = Signal(str)
    edit_file_requested = Signal(str, str)  # server_id, filename
    edit_requested = Signal(str)  # server_id
    delete_requested = Signal(str)  # server_id

    def __init__(self, server: MinecraftServer, events: ServerEvents,
                 history: UsageHistory = usage_history, parent: QWidget | None = None, *,
                 backups: Callable[[MinecraftServer], list[Backup]] = sm.list_backups,
                 choose_export_path: Callable[[QWidget, MinecraftServer], str | None]
                 = pick_export_path) -> None:
        super().__init__(parent)
        self.setObjectName("Page")
        self.server = server
        self._choose_export_path = choose_export_path
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
        side_widget.setFixedWidth(SIDE_WIDTH)
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
        self.export_button = button(_("Export server"), "export", variant="ghost")
        self.export_button.setStyleSheet("text-align: left;")
        self.export_button.clicked.connect(self.export)
        actions.layout_.addWidget(self.export_button)
        self.delete_button = button(_("Delete server"), "delete", variant="ghost",
                                    icon_color=p.danger)
        self.delete_button.setProperty("tone", "danger")
        self.delete_button.setStyleSheet("text-align: left;")
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self.server.id))
        actions.layout_.addWidget(self.delete_button)
        side.addWidget(actions)

        side.addSpacing(s.sm)
        self.backup_list = BackupList(lambda: backups(self.server))
        self.backup_list.backup_requested.connect(self.back_up)
        self.backup_list.open_folder_requested.connect(
            lambda: open_file_explorer(sm.backups_folder(self.server)))
        self.backup_list.restore_requested.connect(self.confirm_restore)
        self.backup_list.delete_requested.connect(self.confirm_delete_backup)
        side.addWidget(self.backup_list)
        side.addStretch(1)

        # The side column scrolls when the window is too short for it
        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        side_scroll.setWidget(side_widget)
        side_scroll.setFixedWidth(SIDE_WIDTH + side_scroll.verticalScrollBar().sizeHint().width())
        body.addWidget(side_scroll)
        root.addLayout(body, 1)

        self.file_buttons: dict[str, QWidget] = {}

        # --------------------------------------------------------- wiring
        self.refresh()
        self.console.set_lines(list(server.output))
        events.output_lines.connect(self._on_output)
        events.state_changed.connect(self._on_state_changed)
        events.server_updated.connect(self._on_server_updated)
        events.busy_changed.connect(self._on_busy_changed)
        events.backups_changed.connect(self._on_backups_changed)

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
            (self._events.busy_changed, self._on_busy_changed),
            (self._events.backups_changed, self._on_backups_changed),
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
        self.badge.set_activity(sm.activity_label(server))
        self.start_button.setEnabled(sm.can_start(server))
        self.stop_button.setEnabled(sm.can_stop(server))
        self.console.set_input_enabled(server.is_active)
        self._refresh_files()
        self._refresh_backup_actions()

    def _refresh_backup_actions(self) -> None:
        server = self.server
        busy = sm.is_busy(server)
        can_backup = sm.can_backup(server)
        if busy:
            reason = sm.activity_label(server)
        elif not can_backup:
            reason = _("Stop the server to back it up or restore a backup")
        else:
            reason = None
        self.backup_list.set_actions_enabled(can_backup, reason, delete_enabled=not busy)
        self.export_button.setEnabled(can_backup)
        self.export_button.setToolTip(
            "" if can_backup else (reason or _("Stop the server to export it")))
        self.delete_button.setEnabled(not busy)
        self.edit_button.setEnabled(not busy)

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

    def _on_busy_changed(self, server_id: str) -> None:
        if server_id == self.server.id:
            self.refresh()

    def _on_backups_changed(self, server_id: str) -> None:
        if server_id == self.server.id:
            self.backup_list.reload()

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

    # -------------------------------------------------------------- backups

    def back_up(self) -> None:
        tracker = FileProgress(_("Backing up server {name}", name=self.server.name))
        run_task(sm.backup_server(self.server, progress=tracker), progress=tracker.text,
                 success=_("Backup created"), tracker=tracker,
                 disable=[self.backup_list.backup_button])

    def confirm_restore(self, backup: Backup) -> None:
        dialog = RestoreBackupDialog(self, self.server, backup)
        dialog.accepted.connect(lambda: self.restore(backup))
        dialog.open()

    def restore(self, backup: Backup) -> None:
        tracker = FileProgress(_("Restoring backup of server {name}", name=self.server.name))
        run_task(sm.restore_backup(self.server, backup, progress=tracker), progress=tracker.text,
                 success=_("Backup restored"), tracker=tracker)

    def confirm_delete_backup(self, backup: Backup) -> None:
        dialog = DeleteBackupDialog(self, backup)
        dialog.accepted.connect(lambda: self.delete_backup(backup))
        dialog.open()

    def delete_backup(self, backup: Backup) -> None:
        run_blocking(sm.delete_backup, backup, success=_("Backup deleted"))

    def export(self) -> None:
        path = self._choose_export_path(self, self.server)
        if not path:
            return
        tracker = FileProgress(_("Exporting server {name}", name=self.server.name))
        run_task(sm.export_server(self.server, path, progress=tracker), progress=tracker.text,
                 success=_("Server exported"), tracker=tracker, disable=[self.export_button])
