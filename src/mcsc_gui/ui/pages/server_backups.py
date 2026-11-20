"""Server backups: "Back up now", the automatic policy and the table of backups."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QWidget

from mcsc import Backup, MinecraftServer

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.os_utils import open_file_explorer
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui import backup_actions
from mcsc_gui.ui.navigator import BACKUPS, SERVER_SETTINGS
from mcsc_gui.ui.pages.server_base import ServerPage
from mcsc_gui.ui.server_events import ServerEvents
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.backup_list import BackupTable
from mcsc_gui.ui.widgets.card import Card
from mcsc_gui.ui.widgets.common import button, label


class ServerBackupsPage(ServerPage):
    section = BACKUPS

    def __init__(self, server: MinecraftServer, events: ServerEvents,
                 parent: QWidget | None = None, *,
                 backups: Callable[[MinecraftServer], list[Backup]] = sm.list_backups) -> None:
        super().__init__(server, events, parent)
        self._load_backups = backups
        s = TOKENS.spacing

        toolbar = QHBoxLayout()
        toolbar.setSpacing(s.sm)
        self.backup_button = button(_("Back up now"), "archive-arrow-down-outline",
                                    variant="primary")
        self.backup_button.clicked.connect(
            lambda: backup_actions.back_up(self.server, [self.backup_button]))
        toolbar.addWidget(self.backup_button)
        self.folder_button = button(_("Open backups folder"), "folder")
        self.folder_button.clicked.connect(
            lambda: open_file_explorer(sm.backups_folder(self.server)))
        toolbar.addWidget(self.folder_button)
        toolbar.addStretch(1)

        policy = Card(padding=s.sm)
        policy_row = QHBoxLayout()
        policy_row.setSpacing(s.md)
        policy_row.addWidget(label(_("AUTOMATIC"), "overline"), 0, Qt.AlignmentFlag.AlignVCenter)
        self.policy_label = label("")
        policy_row.addWidget(self.policy_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.change_button = button(_("Change"), variant="ghost")
        self.change_button.clicked.connect(lambda: self.go_to(SERVER_SETTINGS))
        policy_row.addWidget(self.change_button)
        policy.layout_.addLayout(policy_row)
        toolbar.addWidget(policy)
        self.body.addLayout(toolbar)

        self.table = BackupTable()
        self.table.restore_requested.connect(
            lambda backup: backup_actions.confirm_restore(self, self.server, backup))
        self.table.delete_requested.connect(
            lambda backup: backup_actions.confirm_delete(self, backup))
        self.body.addWidget(self.table, 1)
        self.body.addWidget(label(
            _("Restoring saves the current state first (\"Before restore\"). "
              "Back up and restore need the server stopped."), "muted", wrap=True))

        self.reload()
        self.refresh()

    def reload(self) -> None:
        self.table.set_backups(self._load_backups(self.server))
        self.refresh()

    def refresh(self) -> None:
        super().refresh()
        reason = backup_actions.backup_block_reason(self.server)
        self.backup_button.setEnabled(reason is None)
        self.backup_button.setToolTip(reason or "")
        self.table.set_actions_enabled(reason is None, reason,
                                       delete_enabled=not sm.is_busy(self.server))
        policy = sm.effective_backup_policy(self.server)
        text = _(sm.BACKUP_POLICY_LABELS[policy])
        if policy != "never":
            retention = sm.backup_retention()
            text += " · " + (_("keeps the last {count}", count=retention) if retention
                             else _("keeps all"))
        self.policy_label.setText(text)

    def on_backups_changed(self) -> None:
        self.reload()
