from pathlib import Path
from unittest import mock

import pytest
from PySide6.QtCore import Qt

from mcsc import ServerManager, ServerState

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.server_prefs import ServerPrefs
from mcsc_gui.ui.dialogs.create_server import CreateServerDialog
from mcsc_gui.ui.dialogs.delete_server import DeleteServerDialog
from mcsc_gui.ui.dialogs.edit_server import EditServerDialog
from mcsc_gui.ui.widgets.overlay_dialog import MessageDialog

VERSIONS = {0: ["1.21.4", "1.20.1"], 1: ["1.21.4-232", "1.20.4-499"], 2: []}


def open_create(qtbot, host, calls=None):
    def load(server_type):
        if calls is not None:
            calls.append(server_type)
        return VERSIONS[server_type]

    dialog = CreateServerDialog(host, load_versions=load)
    dialog.open()
    qtbot.waitUntil(lambda: not dialog.loading, timeout=2000)
    return dialog


def test_create_requires_eula_and_name(qtbot, host, bridge):
    dialog = open_create(qtbot, host)
    assert dialog.versions == VERSIONS[0]
    assert dialog.version == "1.21.4"
    assert not dialog.create_button.isEnabled()  # EULA not accepted

    dialog.eula.setChecked(True)
    assert dialog.create_button.isEnabled()

    with mock.patch.object(sm, "create_server") as create:
        dialog.name.widget.setText("   ")
        dialog.submit()
        assert dialog.name.error == "Server name can't be empty"

        dialog.name.widget.setText("x" * 35)
        assert dialog.name.error == "Too long!"  # live validation
        dialog.submit()
        assert dialog.name.error == "Too long!"
        create.assert_not_called()

    dialog.name.widget.setText("x" * 34)
    assert dialog.name.error is None


def test_changing_type_reloads_versions(qtbot, host, bridge):
    calls = []
    dialog = open_create(qtbot, host, calls)
    dialog.type_combo.setCurrentIndex(dialog.type_combo.findData(1))
    qtbot.waitUntil(lambda: not dialog.loading and dialog.versions == VERSIONS[1], timeout=2000)
    assert calls == [0, 1]
    assert dialog.version == "1.21.4-232"

    dialog.type_combo.setCurrentIndex(dialog.type_combo.findData(2))
    qtbot.waitUntil(lambda: not dialog.loading, timeout=2000)
    assert dialog.versions == []
    assert dialog.version_field.error  # "can't load the versions list"


def test_create_success_closes_and_failure_keeps_data(qtbot, host, bridge, make_server):
    dialog = open_create(qtbot, host)
    dialog.eula.setChecked(True)
    dialog.name.widget.setText("Survival")

    async def failing(**kwargs):
        raise ValueError("network down")

    with mock.patch.object(sm, "create_server", new=failing):
        dialog.submit()
        qtbot.waitUntil(lambda: not dialog.busy, timeout=2000)
    assert dialog.result is None  # still open
    assert dialog.name.widget.text() == "Survival"
    assert dialog.create_button.isEnabled()

    created = make_server("created")

    async def ok(**kwargs):
        assert kwargs == {"name": "Survival", "version": "1.21.4", "server_type": 0,
                          "ram_gb": dialog.ram.value(), "accept_eula": True}
        return created

    with mock.patch.object(sm, "create_server", new=ok):
        with qtbot.waitSignal(dialog.created, timeout=2000) as blocker:
            dialog.submit()
    assert blocker.args == ["created"]
    assert dialog.result is True


def test_version_must_come_from_the_list(qtbot, host, bridge):
    dialog = open_create(qtbot, host)
    dialog.eula.setChecked(True)
    dialog.name.widget.setText("ok")
    dialog.version_combo.setEditText("9.9.9")
    with mock.patch.object(sm, "create_server") as create:
        dialog.submit()
    create.assert_not_called()
    assert dialog.version_field.error


def test_delete_button_needs_exact_name(qtbot, host, make_server):
    dialog = DeleteServerDialog(host, make_server(name="My Server"))
    dialog.open()
    assert not dialog.delete_button.isEnabled()
    dialog.confirm_edit.setText("my server")
    assert not dialog.delete_button.isEnabled()
    assert dialog.confirm_field.error == "Wrong name"
    dialog.confirm_edit.setText("My Server")
    assert dialog.delete_button.isEnabled()
    assert dialog.confirm_field.error is None


@pytest.fixture
def registry(tmp_path: Path):
    manager = ServerManager(tmp_path / "servers", tmp_path / "servers.json",
                            backups_dir=tmp_path / "backups")
    with mock.patch.object(sm, "manager", manager), \
            mock.patch.object(sm, "prefs", ServerPrefs(tmp_path / "prefs.json")), \
            mock.patch.object(sm, "send_event_async", new=mock.AsyncMock()):
        yield manager


def test_delete_running_server_shows_error(qtbot, host, bridge, registry, make_server):
    server = registry.register(make_server().config)
    server._state = ServerState.RUNNING  # pylint: disable=protected-access
    errors = []
    dialog = DeleteServerDialog(host, server)
    dialog.open()
    dialog.confirm_edit.setText("Test")
    with mock.patch("mcsc_gui.ui.tasks.error_message", side_effect=lambda e: errors.append(e) or "x"):
        dialog.submit()
        qtbot.waitUntil(lambda: not dialog.busy, timeout=2000)
    assert dialog.result is None
    assert type(errors[0]).__name__ == "ServerRunningError"
    assert registry.find("srv") is not None


def test_delete_stopped_server(qtbot, host, bridge, registry, make_server):
    server = registry.register(make_server().config)
    dialog = DeleteServerDialog(host, server)
    dialog.open()
    dialog.confirm_edit.setText("Test")
    dialog.delete_files.setChecked(True)
    with qtbot.waitSignal(dialog.deleted, timeout=2000):
        dialog.submit()
    assert registry.find("srv") is None
    assert not server.path.exists()


def test_edit_slider_keeps_ram_above_system_total(qtbot, host, make_server):
    server = make_server()
    server.config.ram_gb = 4096
    dialog = EditServerDialog(host, server)
    dialog.open()
    assert dialog.ram.maximum() == 4096
    assert dialog.ram.value() == 4096
    assert not dialog.eula.isEnabled()


def test_edit_saves_name_and_ram(qtbot, host, bridge, registry, make_server):
    server = registry.register(make_server().config)
    dialog = EditServerDialog(host, server)
    dialog.open()
    dialog.name.widget.setText("Renamed")
    dialog.ram.setValue(1)
    with qtbot.waitSignal(dialog.accepted, timeout=2000):
        dialog.submit()
    assert server.config.name == "Renamed"
    assert server.config.ram_gb == 1


def test_overlay_escape_and_focus_trap(qtbot, host):
    dialog = MessageDialog(host, "Title", "Body", confirm="Yes", cancel="No")
    dialog.open()
    qtbot.waitUntil(lambda: dialog.focusWidget() is not None, timeout=1000)
    focusable = dialog._focusable()  # pylint: disable=protected-access
    assert dialog.cancel_button in focusable and dialog.confirm_button in focusable
    for _ in range(len(focusable) + 2):  # Tab never leaves the panel
        dialog.focusNextPrevChild(True)
        assert dialog.panel.isAncestorOf(dialog.focusWidget())

    with qtbot.waitSignal(dialog.rejected, timeout=1000):
        qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert dialog.result is False


def test_busy_dialog_ignores_escape(qtbot, host):
    dialog = MessageDialog(host, "Title", "Body", confirm="Yes", cancel="No")
    dialog.open()
    dialog.set_busy(True)
    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert dialog.result is None


def test_update_dialog_requests_update(qtbot, host):
    from mcsc_gui.ui.dialogs.update_app import UpdateAppDialog  # pylint: disable=import-outside-toplevel

    dialog = UpdateAppDialog(host)
    dialog.open()
    with qtbot.waitSignal(dialog.update_requested, timeout=1000):
        dialog.update_button.click()
    assert dialog.result is True
