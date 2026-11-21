"""Backup confirmations: restore (the current state is saved first) and delete."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from mcsc import Backup, MinecraftServer

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.widgets.backup_list import format_date
from mcsc_gui.ui.widgets.overlay_dialog import MessageDialog


class RestoreBackupDialog(MessageDialog):
    """Asks to confirm a restore. ``accepted`` means "restore it"."""

    def __init__(self, parent: QWidget, server: MinecraftServer, backup: Backup) -> None:
        details = f"{format_date(backup)} · {sm.backup_kind_label(backup.kind)} · " \
                  f"{backup.server_type.label} {backup.version}"
        message = _(
            "The files of '{name}' will be replaced with this backup:\n{details}\n\n"
            "The current state is backed up first (\"Before restore\"), "
            "so you can go back to it.",
            name=server.name, details=details,
        )
        if backup.version != server.config.version:
            message += "\n\n" + _("The server version will change from {old} to {new}.",
                                  old=server.config.version, new=backup.version)
        super().__init__(parent, _("Restore backup?"), message, confirm=_("Restore"),
                         cancel=_("Cancel"), confirm_icon="backup-restore")
        self.server = server
        self.backup = backup


class DeleteBackupDialog(MessageDialog):
    """Asks to confirm deleting a backup. ``accepted`` means "delete it"."""

    def __init__(self, parent: QWidget, backup: Backup) -> None:
        super().__init__(
            parent, _("Delete backup?"),
            _("The backup of {date} will be deleted. This can't be undone.",
              date=format_date(backup)),
            confirm=_("Delete"), cancel=_("Cancel"), confirm_variant="danger",
            confirm_icon="delete",
        )
        self.cancel_button.setDefault(True)
        self.confirm_button.setDefault(False)
        self.backup = backup
