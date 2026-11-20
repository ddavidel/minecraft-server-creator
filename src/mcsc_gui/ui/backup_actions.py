"""Backup, restore, delete and export from the UI (shared by the server pages)."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QWidget

from mcsc import Backup, MinecraftServer

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.dialogs.restore_backup import DeleteBackupDialog, RestoreBackupDialog
from mcsc_gui.ui.tasks import FileProgress, run_blocking, run_task

_UNSAFE_FILE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def backup_block_reason(server: MinecraftServer) -> str | None:
    """Why backup/restore/export are disabled now (``None`` if they're possible)."""
    if sm.is_busy(server):
        return sm.activity_label(server)
    if not sm.can_backup(server):
        return _("Stop the server to back it up or restore a backup")
    return None


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


def back_up(server: MinecraftServer, disable: Iterable[QWidget] = ()) -> None:
    tracker = FileProgress(_("Backing up server {name}", name=server.name))
    run_task(sm.backup_server(server, progress=tracker), progress=tracker.text,
             success=_("Backup created"), tracker=tracker, disable=disable)


def confirm_restore(parent: QWidget, server: MinecraftServer, backup: Backup) -> None:
    dialog = RestoreBackupDialog(parent, server, backup)
    dialog.accepted.connect(lambda: restore(server, backup))
    dialog.open()


def restore(server: MinecraftServer, backup: Backup) -> None:
    tracker = FileProgress(_("Restoring backup of server {name}", name=server.name))
    run_task(sm.restore_backup(server, backup, progress=tracker), progress=tracker.text,
             success=_("Backup restored"), tracker=tracker)


def confirm_delete(parent: QWidget, backup: Backup) -> None:
    dialog = DeleteBackupDialog(parent, backup)
    dialog.accepted.connect(lambda: run_blocking(sm.delete_backup, backup,
                                                 success=_("Backup deleted")))
    dialog.open()


def export(server: MinecraftServer, path: str, disable: Iterable[QWidget] = ()) -> None:
    tracker = FileProgress(_("Exporting server {name}", name=server.name))
    run_task(sm.export_server(server, path, progress=tracker), progress=tracker.text,
             success=_("Server exported"), tracker=tracker, disable=disable)
