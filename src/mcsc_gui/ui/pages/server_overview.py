"""Server overview: resources, read-only logs, connection, latest backups, config files."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from mcsc import Backup, MinecraftServer, ServerState

from mcsc_gui.config import settings as mcssettings
from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui import backup_actions
from mcsc_gui.ui.config_files import config_file_label, visible_config_files
from mcsc_gui.ui.navigator import BACKUPS, CONFIGURATION, CONSOLE, SERVER
from mcsc_gui.ui.pages.server_base import ServerPage
from mcsc_gui.ui.server_events import ServerEvents
from mcsc_gui.ui.tasks import toasts
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.usage import UsageHistory, usage_history
from mcsc_gui.ui.widgets.backup_list import RecentBackups
from mcsc_gui.ui.widgets.card import Card
from mcsc_gui.ui.widgets.common import button, icon_button, label
from mcsc_gui.ui.widgets.console import ConsoleView
from mcsc_gui.ui.widgets.stat_tile import StatTile

USAGE_INTERVAL_MS = 1000
SIDE_WIDTH = 380


def _card_title(text: str, action: QWidget | None = None) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(TOKENS.spacing.sm)
    row.addWidget(label(text, "overline"), 1)
    if action is not None:
        row.addWidget(action)
    return row


class ServerOverviewPage(ServerPage):
    """Landing page of a server. The logs are read-only: commands go in the console."""

    section = SERVER

    def __init__(self, server: MinecraftServer, events: ServerEvents,
                 history: UsageHistory = usage_history, parent: QWidget | None = None, *,
                 backups: Callable[[MinecraftServer], list[Backup]] = sm.list_backups) -> None:
        super().__init__(server, events, parent)
        self._history = history
        self._load_backups = backups
        s = TOKENS.spacing
        p = TOKENS.palette

        # ------------------------------------------------------- resources
        stats = QGridLayout()
        stats.setSpacing(s.md)
        self.ram_tile = StatTile("donut_large", _("RAM usage"), "MB", p.accent, row=True)
        self.cpu_tile = StatTile("memory", _("CPU usage"), "%", p.info, row=True)
        self.read_tile = StatTile("disk_read", _("Disk read"), "MB/s", p.warning, row=True)
        self.write_tile = StatTile("disk_write", _("Disk write"), "MB/s", p.dirt, row=True)
        for column, tile in enumerate((self.ram_tile, self.cpu_tile, self.read_tile,
                                       self.write_tile)):
            stats.addWidget(tile, 0, column)
            stats.setColumnStretch(column, 1)
        self.body.addLayout(stats)

        content = QHBoxLayout()
        content.setSpacing(s.lg)

        # ------------------------------------------------------------- logs
        logs = QVBoxLayout()
        logs.setSpacing(s.sm)
        self.console_link = button(_("Open console"), "terminal", variant="ghost")
        self.console_link.clicked.connect(lambda: self.go_to(CONSOLE))
        logs.addLayout(_card_title(_("LOGS"), self.console_link))
        self.logs = ConsoleView(mcssettings.MAX_LOG_LINES, read_only=True)
        logs.addWidget(self.logs, 1)
        content.addLayout(logs, 1)

        # ------------------------------------------------------- side cards
        side = QVBoxLayout()
        side.setSpacing(s.md)
        side_widget = QWidget()
        side_widget.setFixedWidth(SIDE_WIDTH)
        side_widget.setLayout(side)
        side.setContentsMargins(0, 0, 0, 0)

        connection = Card(padding=s.md)
        connection.layout_.setSpacing(s.sm)
        connection.layout_.addLayout(_card_title(_("CONNECTION")))
        address_row = QHBoxLayout()
        address_row.setSpacing(s.sm)
        self.address_label = label("", "title")
        self.address_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        address_row.addWidget(self.address_label, 1)
        self.copy_button = icon_button("content-copy", _("Copy address"))
        self.copy_button.clicked.connect(self.copy_address)
        address_row.addWidget(self.copy_button)
        connection.layout_.addLayout(address_row)
        connection.layout_.addWidget(
            label(_("Players on your network join with this address."), "muted", wrap=True))
        side.addWidget(connection)

        backups_card = Card(padding=s.md)
        backups_card.layout_.setSpacing(s.sm)
        self.all_backups_button = button(_("All backups"), variant="ghost")
        self.all_backups_button.clicked.connect(lambda: self.go_to(BACKUPS))
        backups_card.layout_.addLayout(_card_title(_("BACKUPS"), self.all_backups_button))
        self.recent_backups = RecentBackups()
        backups_card.layout_.addWidget(self.recent_backups)
        backup_row = QHBoxLayout()
        backup_row.setSpacing(s.sm)
        self.backup_button = button(_("Back up now"), "archive-arrow-down-outline")
        self.backup_button.clicked.connect(
            lambda: backup_actions.back_up(self.server, [self.backup_button]))
        backup_row.addWidget(self.backup_button)
        self.policy_label = label("", "mono", wrap=True)
        backup_row.addWidget(self.policy_label, 1)
        backups_card.layout_.addLayout(backup_row)
        side.addWidget(backups_card)

        files_card = Card(padding=s.md)
        files_card.layout_.setSpacing(2)
        self.configuration_button = button(_("Open"), variant="ghost")
        self.configuration_button.clicked.connect(lambda: self.go_to(CONFIGURATION))
        files_card.layout_.addLayout(_card_title(_("CONFIGURATION"), self.configuration_button))
        self._files_layout = QVBoxLayout()
        self._files_layout.setSpacing(2)
        files_card.layout_.addLayout(self._files_layout)
        self.file_buttons: dict[str, QWidget] = {}
        side.addWidget(files_card)
        side.addStretch(1)
        content.addWidget(side_widget)
        self.body.addLayout(content, 1)

        # ----------------------------------------------------------- wiring
        self.logs.set_lines(list(server.output))
        self.reload_backups()
        self.refresh()
        self.usage_timer = QTimer(self)
        self.usage_timer.setInterval(USAGE_INTERVAL_MS)
        self.usage_timer.timeout.connect(self._sample_usage)
        self.usage_timer.start()
        self._sample_usage()

    # ----------------------------------------------------------------- state

    def refresh(self) -> None:
        super().refresh()
        self.address_label.setText(sm.connection_address(self.server))
        reason = backup_actions.backup_block_reason(self.server)
        self.backup_button.setEnabled(reason is None)
        self.backup_button.setToolTip(reason or "")
        self.policy_label.setText(_("Automatic: {policy}", policy=_(
            sm.BACKUP_POLICY_LABELS[sm.effective_backup_policy(self.server)])))
        self._refresh_files()

    def reload_backups(self) -> None:
        backups = self._load_backups(self.server)
        self.recent_backups.set_backups(backups)
        self.all_backups_button.setText(_("All backups ({count})", count=len(backups)))

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
                    lambda _c=False, f=filename: self.edit_file_requested.emit(self.server.id, f))
                self._files_layout.addWidget(btn)
                self.file_buttons[filename] = btn
        for filename, enabled in files:
            self.file_buttons[filename].setEnabled(enabled)

    def copy_address(self) -> None:
        QGuiApplication.clipboard().setText(self.address_label.text())
        manager = toasts()
        if manager is not None:
            manager.success(_("Address copied"))

    # ----------------------------------------------------------------- hooks

    def on_state_changed(self, old: str, new: str) -> None:
        if new == ServerState.STARTING:
            self.logs.set_lines([])  # pymcsc clears its buffer on start
            self._history.reset(self.server.id)
        elif new == ServerState.STOPPED:
            self._history.reset(self.server.id)
            self._sample_usage()

    def on_output(self, lines: list) -> None:
        self.logs.append_lines(lines)

    def on_backups_changed(self) -> None:
        self.reload_backups()

    def on_dispose(self) -> None:
        self.usage_timer.stop()

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
