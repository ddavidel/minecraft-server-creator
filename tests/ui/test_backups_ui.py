from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import pytest

from mcsc import ArchiveInfo, Backup, BackupKind, BackupManifest, DetectedServer, ServerType

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.server_prefs import ServerPrefs
from mcsc_gui.ui.dialogs.app_settings import AppSettingsDialog
from mcsc_gui.ui.dialogs.confirm_quit import ConfirmQuitDialog, ShutdownDialog
from mcsc_gui.ui.dialogs.delete_server import DeleteServerDialog
from mcsc_gui.ui.dialogs.import_server import ImportServerDialog
from mcsc_gui.ui.dialogs.restore_backup import RestoreBackupDialog
from mcsc_gui.ui.widgets.backup_list import format_size


def make_backup(server, kind=BackupKind.MANUAL, version="1.21.4", name="20261120-101500"):
    return Backup(path=Path(f"/backups/{server.id}/{name}_{kind}.zip"), server_id=server.id,
                  kind=kind, created_at=datetime(2026, 11, 20, 10, 15, tzinfo=UTC),
                  version=version, server_type=ServerType.PAPER, size_bytes=5 * 1024 * 1024)


@pytest.fixture
def prefs(tmp_path):
    with mock.patch.object(sm, "prefs", ServerPrefs(tmp_path / "prefs.json")) as p:
        yield p


def test_format_size():
    assert format_size(512) == "512 B"
    assert format_size(5 * 1024 * 1024) == "5.0 MB"
    assert format_size(3 * 1024 ** 3) == "3.0 GB"


def test_restore_dialog_warns_about_version_change(host, make_server):
    server = make_server()
    dialog = RestoreBackupDialog(host, server, make_backup(server, version="1.20.1"))
    assert "1.21.4" in dialog.message_label.text() and "1.20.1" in dialog.message_label.text()


# ------------------------------------------------------------------ import


def archive_info(path):
    manifest = BackupManifest(kind=BackupKind.EXPORT, server={
        "id": "old", "name": "Survival", "version": "1.21.4", "server_type": 1, "ram_gb": 1,
    }, file_count=12, size_bytes=2048)
    return ArchiveInfo(path=Path(path), manifest=manifest, eula_accepted=True,
                       suggested_name="Survival (2)", archive_size=1024)


def test_import_archive(qtbot, host, bridge, make_server):
    dialog = ImportServerDialog(host, choose_archive=lambda _p: "C:/exports/survival.zip")
    dialog.open()
    assert not dialog.import_button.isEnabled()
    created = make_server("new")
    with mock.patch.object(sm, "inspect_archive", side_effect=archive_info), \
            mock.patch.object(sm, "import_server", new=mock.AsyncMock(return_value=created)) as imp:
        dialog.archive_button.click()
        qtbot.waitUntil(lambda: dialog.source == "archive", timeout=2000)
        assert dialog.name.widget.text() == "Survival (2)"
        assert dialog.eula.isChecked()  # pre-checked, the user can still uncheck it
        assert dialog.ram.value() == 1
        assert not dialog.version_edit.isEnabled()
        assert dialog.import_button.isEnabled()
        with qtbot.waitSignal(dialog.imported, timeout=2000) as blocker:
            dialog.submit()
    assert blocker.args == ["new"]
    args = imp.call_args
    assert args.args == ("C:/exports/survival.zip", "Survival (2)", 1, True)


def test_import_invalid_archive_shows_error(qtbot, host, bridge):
    from mcsc import InvalidArchiveError  # pylint: disable=import-outside-toplevel

    dialog = ImportServerDialog(host)
    dialog.open()
    with mock.patch.object(sm, "inspect_archive", side_effect=InvalidArchiveError("bad")):
        dialog.load_archive("bad.zip")
        qtbot.waitUntil(lambda: dialog.error_label.isVisibleTo(dialog), timeout=2000)
    assert dialog.error_label.text() == "This file is not a valid MCSC backup or export"
    assert dialog.source is None and not dialog.import_button.isEnabled()


def test_import_folder(qtbot, host, bridge, make_server):
    dialog = ImportServerDialog(host, choose_folder=lambda _p: "C:/mc/My World")
    dialog.open()
    detected = DetectedServer(ServerType.VANILLA, None, Path("minecraft_server.jar"))
    created = make_server("new")
    with mock.patch.object(sm, "detect_folder", return_value=detected), \
            mock.patch.object(sm, "import_server_folder",
                              new=mock.AsyncMock(return_value=created)) as imp:
        dialog.folder_button.click()
        qtbot.waitUntil(lambda: dialog.source == "folder", timeout=2000)
        assert dialog.name.widget.text() == "My World"
        assert dialog.version_edit.isEnabled() and dialog.version_edit.text() == ""
        dialog.submit()
        assert dialog.version_field.error  # version is required when it can't be detected
        imp.assert_not_called()
        dialog.version_edit.setText("1.21.4")
        with qtbot.waitSignal(dialog.imported, timeout=2000):
            dialog.submit()
    assert imp.call_args.args[:3] == ("C:/mc/My World", ServerType.VANILLA, "1.21.4")
    assert imp.call_args.kwargs == {"jar": Path("minecraft_server.jar")}


def test_import_folder_not_a_server(qtbot, host, bridge):
    dialog = ImportServerDialog(host)
    dialog.open()
    with mock.patch.object(sm, "detect_folder", return_value=DetectedServer(None, None, None)):
        dialog.load_folder("C:/empty")
        qtbot.waitUntil(lambda: dialog.error_label.isVisibleTo(dialog), timeout=2000)
    assert dialog.source is None


# ----------------------------------------------------------------- settings


def test_app_settings_include_backup_settings(qtbot, host):
    settings = mock.Mock(user_settings={"auto_backup": "on_start", "backup_retention": 0})
    dialog = AppSettingsDialog(host, user_settings=settings)
    values = dialog.values()
    assert values["auto_backup"] == "on_start"
    assert values["backup_retention"] == 0
    assert dialog.backup_retention.text() == "Unlimited"


def test_delete_backups_checkbox_needs_delete_files(host, make_server):
    dialog = DeleteServerDialog(host, make_server())
    assert not dialog.delete_backups.isEnabled()
    dialog.delete_files.setChecked(True)
    assert dialog.delete_backups.isEnabled()
    dialog.delete_backups.setChecked(True)
    dialog.delete_files.setChecked(False)
    assert not dialog.delete_backups.isChecked()


def test_quit_dialogs_mention_operations(host):
    assert "in progress" in ConfirmQuitDialog(host, operations=True).message_label.text()
    assert "backing up" in ShutdownDialog(host, backing_up=True).message.text()
