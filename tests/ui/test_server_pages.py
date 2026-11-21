import gc
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import pytest
from PySide6.QtCore import SIGNAL
from PySide6.QtWidgets import QStackedWidget, QWidget

from mcsc import Backup, BackupKind, ResourceUsage, ServerState, ServerType

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.server_prefs import ServerPrefs
from mcsc_gui.ui.dialogs.restore_backup import RestoreBackupDialog
from mcsc_gui.ui.navigator import (
    BACKUPS,
    CONFIGURATION,
    CONSOLE,
    DASHBOARD,
    EDITOR,
    SERVER,
    SERVER_SETTINGS,
    Navigator,
    Route,
    section_of,
)
from mcsc_gui.ui.pages.server_backups import ServerBackupsPage
from mcsc_gui.ui.pages.server_configuration import ServerConfigurationPage
from mcsc_gui.ui.pages.server_console import ServerConsolePage
from mcsc_gui.ui.pages.server_overview import ServerOverviewPage
from mcsc_gui.ui.pages.server_settings import ServerSettingsPage
from mcsc_gui.ui.server_events import ServerEvents
from mcsc_gui.ui.usage import UsageHistory
from mcsc_gui.ui.widgets.sidebar import Sidebar


def make_backup(server, kind=BackupKind.MANUAL, day=20):
    return Backup(path=Path(f"/backups/{server.id}/202611{day}-101500_{kind}.zip"),
                  server_id=server.id, kind=kind,
                  created_at=datetime(2026, 11, day, 10, 15, tzinfo=UTC), version="1.21.4",
                  server_type=ServerType.PAPER, size_bytes=5 * 1024 * 1024)


@pytest.fixture
def prefs(tmp_path):
    with mock.patch.object(sm, "prefs", ServerPrefs(tmp_path / "prefs.json")) as p, \
            mock.patch.object(sm, "_settings", lambda: {}):
        yield p


@pytest.fixture
def events():
    e = ServerEvents(track_registry=False)
    yield e
    e.close()


@pytest.fixture
def server(make_server, events, prefs):
    s = make_server()
    events.attach(s)
    return s


def open_page(qtbot, page):
    qtbot.addWidget(page)
    page.resize(1100, 760)
    page.show()
    return page


# --------------------------------------------------------------- navigation


def test_sections_are_siblings_and_the_editor_is_pushed(qtbot):
    stack = QStackedWidget()
    qtbot.addWidget(stack)
    navigator = Navigator(stack, QWidget(), lambda route: QWidget(), animate=False)
    navigator.to_server("s")
    navigator.to_section("s", BACKUPS)
    navigator.to_section("s", CONFIGURATION)
    assert navigator.history == [Route(DASHBOARD), Route(CONFIGURATION, ("s",))]
    navigator.to_editor("s", "server.properties")
    navigator.back()
    assert navigator.current_route == Route(CONFIGURATION, ("s",))
    navigator.back()
    assert navigator.current_route == Route(DASHBOARD)
    with pytest.raises(ValueError):
        navigator.to_section("s", EDITOR)


def test_section_of():
    assert section_of(Route(SERVER, ("s",))) == SERVER
    assert section_of(Route(EDITOR, ("s", "x"))) == CONFIGURATION
    assert section_of(Route(DASHBOARD)) is None


def receivers(events: ServerEvents) -> int:
    return sum(events.receivers(SIGNAL(sig)) for sig in (
        "output_lines(QString,QVariantList)", "state_changed(QString,QString,QString)",
        "busy_changed(QString)", "backups_changed(QString)", "server_updated(QString)"))


def test_switching_sections_50_times_leaves_no_listeners(qtbot, server, events):
    """SC-004: entering/leaving server pages doesn't leak listeners or pages."""
    pages = {SERVER: lambda: ServerOverviewPage(server, events, history=UsageHistory(),
                                                backups=lambda _s: []),
             CONSOLE: lambda: ServerConsolePage(server, events),
             BACKUPS: lambda: ServerBackupsPage(server, events, backups=lambda _s: [])}
    stack = QStackedWidget()
    qtbot.addWidget(stack)
    navigator = Navigator(stack, QWidget(), lambda route: pages[route.kind](), animate=False)
    baseline = receivers(events)
    for _ in range(50):
        for section in pages:
            navigator.to_section(server.id, section)
        navigator.to_dashboard()
    qtbot.wait(10)
    gc.collect()
    assert receivers(events) == baseline
    assert stack.count() == 1
    assert len(server._output_listeners) == 1  # pylint: disable=protected-access


# ------------------------------------------------------------------ sidebar


def test_sidebar_switches_between_app_and_server_menu(qtbot, server):
    sidebar = Sidebar()
    qtbot.addWidget(sidebar)
    assert not sidebar.showing_server
    sidebar.show_server(server, BACKUPS)
    assert sidebar.showing_server
    assert sidebar.server_name.text() == "Test"
    assert sidebar.section_buttons[BACKUPS].isChecked()
    assert not sidebar.section_buttons[SERVER].isChecked()
    assert list(sidebar.section_buttons) == [SERVER, CONSOLE, CONFIGURATION, BACKUPS,
                                             SERVER_SETTINGS]

    with qtbot.waitSignal(sidebar.section_clicked) as blocker:
        sidebar.section_buttons[CONSOLE].click()
    assert blocker.args == [server.id, CONSOLE]
    assert not sidebar.section_buttons[CONSOLE].isChecked()  # until the page changes

    server._state = ServerState.RUNNING  # pylint: disable=protected-access
    sidebar.refresh_server("other")
    assert sidebar.server_badge.state is ServerState.STOPPED
    sidebar.refresh_server(server.id)
    assert sidebar.server_badge.state is ServerState.RUNNING

    sidebar.show_app_menu()
    assert not sidebar.showing_server and sidebar.server is None


# ----------------------------------------------------------------- overview


def test_overview_shows_read_only_logs_resources_and_backups(qtbot, server, events):
    server.output.extend(["old 1", "old 2"])
    backups = [make_backup(server, day=d) for d in (20, 19, 18, 17)]
    page = open_page(qtbot, ServerOverviewPage(server, events, history=UsageHistory(),
                                               backups=lambda _s: backups))
    try:
        assert page.logs.line_count() == 2
        assert page.logs.input.isHidden()  # no commands from the overview
        assert len(page.recent_backups.lines) == 3
        assert page.all_backups_button.text() == "All backups (4)"
        assert page.address_label.text().endswith(":25565")
        assert page.backup_button.isEnabled()  # stopped: can back up

        with qtbot.waitSignal(events.state_changed, timeout=1000):
            server._set_state(ServerState.STARTING)  # pylint: disable=protected-access
        assert page.logs.line_count() == 0
        assert not page.backup_button.isEnabled()
        server._notify(server._output_listeners, "hello")  # pylint: disable=protected-access
        qtbot.waitUntil(lambda: page.logs.log.toPlainText() == "hello", timeout=1000)

        server.monitor.usage = ResourceUsage(ram_mb=512, cpu_percent=12.5)
        page._sample_usage()  # pylint: disable=protected-access
        assert page.ram_tile.value_label.text() == "512 MB"
        assert page.cpu_tile.value_label.text() == "12.5 %"

        with qtbot.waitSignal(page.section_requested) as blocker:
            page.all_backups_button.click()
        assert blocker.args == [server.id, BACKUPS]
        with qtbot.waitSignal(page.section_requested) as blocker:
            page.console_link.click()
        assert blocker.args == [server.id, CONSOLE]
    finally:
        page.dispose()


def test_overview_config_files_open_the_editor(qtbot, server, events):
    page = open_page(qtbot, ServerOverviewPage(server, events, history=UsageHistory(),
                                               backups=lambda _s: []))
    try:
        assert list(page.file_buttons) == ["server.properties"]
        assert not page.file_buttons["server.properties"].isEnabled()  # before the first start
        (server.server_dir / "server.properties").write_text("motd=x\n", encoding="utf-8")
        page.refresh()
        with qtbot.waitSignal(page.edit_file_requested) as blocker:
            page.file_buttons["server.properties"].click()
        assert blocker.args == [server.id, "server.properties"]
    finally:
        page.dispose()


# ------------------------------------------------------------------ console


def test_console_page_sends_commands_while_running(qtbot, bridge, server, events):
    page = open_page(qtbot, ServerConsolePage(server, events))
    try:
        assert not page.console.input.isEnabled()
        with qtbot.waitSignal(events.state_changed, timeout=1000):
            server._set_state(ServerState.RUNNING)  # pylint: disable=protected-access
        assert page.console.input.isEnabled()
        with mock.patch.object(sm, "send_command", new=mock.AsyncMock()) as send:
            page.console.command_submitted.emit("say hi")
            qtbot.waitUntil(lambda: send.await_count == 1, timeout=2000)
        assert send.call_args.args == (server, "say hi")
        assert page.page_title() == "Test · Console"
    finally:
        page.dispose()


# ------------------------------------------------------------ configuration


def test_configuration_lists_the_files(qtbot, server, events):
    page = open_page(qtbot, ServerConfigurationPage(server, events))
    try:
        row = page.rows["server.properties"]
        assert not row.edit_button.isEnabled() and not row.hint_label.isHidden()
        (server.server_dir / "server.properties").write_text("motd=x\n", encoding="utf-8")
        (server.server_dir / "spigot.yml").write_text("a: 1\n", encoding="utf-8")
        page.refresh()
        assert list(page.rows) == ["server.properties", "spigot.yml"]
        with qtbot.waitSignal(page.edit_file_requested) as blocker:
            page.rows["spigot.yml"].edit_button.click()
        assert blocker.args == [server.id, "spigot.yml"]
    finally:
        page.dispose()


# ------------------------------------------------------------------ backups


@pytest.fixture
def backups_page(qtbot, server, events):
    backups = [make_backup(server), make_backup(server, BackupKind.AUTOMATIC, day=19)]
    page = open_page(qtbot, ServerBackupsPage(server, events, backups=lambda _s: backups))
    yield page, backups
    page.dispose()


def test_backups_page_lists_and_reloads(backups_page, server, events):
    page, backups = backups_page
    rows = page.table.rows
    assert [r.backup for r in rows] == backups
    assert rows[0].kind_label.text() == "Manual"
    assert rows[0].size_label.text() == "5.0 MB"
    assert page.policy_label.text() == "Never"
    backups.clear()
    events.backups_changed.emit("other")
    assert len(page.table.rows) == 2
    events.backups_changed.emit(server.id)
    assert page.table.rows == [] and not page.table.empty_state.isHidden()
    assert page.table.header.isHidden()  # no column titles over an empty table


def test_backups_page_follows_state_and_busy(qtbot, backups_page, server, events):
    page, _backups = backups_page
    with qtbot.waitSignal(events.state_changed, timeout=1000):
        server._set_state(ServerState.RUNNING)  # pylint: disable=protected-access
    row = page.table.rows[0]
    assert not page.backup_button.isEnabled()
    assert not row.restore_button.isEnabled()
    assert "Stop the server" in row.restore_button.toolTip()
    assert row.delete_button.isEnabled()

    server._state = ServerState.STOPPED  # pylint: disable=protected-access
    sm._operations[server.id] = "backup"  # pylint: disable=protected-access
    try:
        events.busy_changed.emit(server.id)
        assert page.header.badge.text == "Backing up…"
        assert not page.header.start_button.isEnabled()
        assert not row.delete_button.isEnabled()
    finally:
        sm._operations.clear()  # pylint: disable=protected-access
    events.busy_changed.emit(server.id)
    assert page.backup_button.isEnabled() and row.restore_button.isEnabled()


def test_backups_page_actions(qtbot, bridge, backups_page, server):
    page, backups = backups_page
    with mock.patch.object(sm, "backup_server", new=mock.AsyncMock()) as backup, \
            mock.patch.object(sm, "restore_backup", new=mock.AsyncMock()) as restore:
        page.backup_button.click()
        qtbot.waitUntil(lambda: backup.await_count == 1, timeout=2000)
        page.table.rows[1].restore_button.click()
        dialog = page.window().findChild(RestoreBackupDialog)
        dialog.confirm_button.click()
        qtbot.waitUntil(lambda: restore.await_count == 1, timeout=2000)
    assert backup.call_args.args == (server,)
    assert restore.call_args.args == (server, backups[1])
    with qtbot.waitSignal(page.section_requested) as blocker:
        page.change_button.click()
    assert blocker.args == [server.id, SERVER_SETTINGS]


# ----------------------------------------------------------------- settings


def test_settings_page_saves_name_ram_and_policy(qtbot, bridge, server, events):
    page = open_page(qtbot, ServerSettingsPage(server, events))
    try:
        assert page.auto_backup.currentData() == "default"
        assert "Never" in page.auto_backup.currentText()  # shows the app default
        page.name.widget.setText("Renamed")
        page.ram.setValue(1)
        page.auto_backup.setCurrentIndex(page.auto_backup.findData("on_stop"))
        with mock.patch.object(sm.manager, "save"):
            page.save()
            qtbot.waitUntil(lambda: server.config.name == "Renamed", timeout=2000)
        assert server.config.ram_gb == 1
        assert sm.server_backup_policy(server) == "on_stop"

        page.name.widget.setText(" ")
        page.save()
        assert page.name.error == "Server name can't be empty"
    finally:
        page.dispose()


def test_settings_page_keeps_ram_above_system_total(qtbot, server, events):
    server.config.ram_gb = 4096
    page = open_page(qtbot, ServerSettingsPage(server, events))
    try:
        assert page.ram.maximum() == 4096 and page.ram.value() == 4096
        assert not page.eula.isEnabled()
    finally:
        page.dispose()


def test_settings_page_export_and_delete(qtbot, bridge, server, events):
    page = open_page(qtbot, ServerSettingsPage(
        server, events, choose_export_path=lambda _p, _s: "out.zip"))
    try:
        with mock.patch.object(sm, "export_server", new=mock.AsyncMock()) as export:
            page.export_button.click()
            qtbot.waitUntil(lambda: export.await_count == 1, timeout=2000)
        assert export.call_args.args == (server, "out.zip")
        with qtbot.waitSignal(page.delete_requested) as blocker:
            page.delete_button.click()
        assert blocker.args == [server.id]

        server._state = ServerState.RUNNING  # pylint: disable=protected-access
        page.refresh()
        assert not page.export_button.isEnabled()
        assert page.delete_button.isEnabled()  # the dialog explains it must be stopped
    finally:
        page.dispose()


def test_settings_page_clone(qtbot, server, events):
    page = open_page(qtbot, ServerSettingsPage(server, events))
    try:
        assert page.clone_button.isEnabled()
        with qtbot.waitSignal(page.clone_requested) as blocker:
            page.clone_button.click()
        assert blocker.args == [server.id]

        server._state = ServerState.RUNNING  # pylint: disable=protected-access
        page.refresh()
        assert not page.clone_button.isEnabled()
        assert page.clone_button.toolTip() == "Stop the server to clone it"
    finally:
        page.dispose()


def test_page_title_follows_renames(qtbot, server, events):
    page = open_page(qtbot, ServerBackupsPage(server, events, backups=lambda _s: []))
    try:
        server.config.name = "New name"
        with qtbot.waitSignal(page.title_changed) as blocker:
            events.server_updated.emit(server.id)
        assert blocker.args == ["New name · Backups"]
        assert page.header.name_label.text() == "New name"
    finally:
        page.dispose()


# -------------------------------------------------------------- main window


def test_main_window_sidebar_follows_server_pages(qtbot, bridge, tmp_path, make_server, prefs):
    from mcsc import ServerManager  # pylint: disable=import-outside-toplevel

    from mcsc_gui.ui.main_window import MainWindow  # pylint: disable=import-outside-toplevel

    manager = ServerManager(tmp_path / "servers", tmp_path / "servers.json",
                            backups_dir=tmp_path / "backups")
    server = manager.register(make_server().config)
    events = ServerEvents(track_registry=False)
    events.attach(server)
    with mock.patch.object(sm, "manager", manager):
        window = MainWindow(events, bridge, native_title_bar=True)
        qtbot.addWidget(window)
        try:
            assert not window.sidebar.showing_server
            window.navigator.to_server(server.id)
            assert isinstance(window.navigator.current_page, ServerOverviewPage)
            assert window.sidebar.showing_server
            assert window.sidebar.section_buttons[SERVER].isChecked()

            window.sidebar.section_buttons[BACKUPS].click()
            assert isinstance(window.navigator.current_page, ServerBackupsPage)
            assert window.sidebar.section_buttons[BACKUPS].isChecked()
            assert window.title_bar.title_label.text() == "Test · Backups"

            window.navigator.to_editor(server.id, "server.properties")
            assert window.sidebar.section_buttons[CONFIGURATION].isChecked()

            window.sidebar.back_button.click()
            assert window.navigator.current_route == Route(DASHBOARD)
            assert not window.sidebar.showing_server
        finally:
            events.close()


def test_main_window_dashboard_menu_and_clone(qtbot, bridge, tmp_path, make_server, prefs):
    from mcsc import ServerManager  # pylint: disable=import-outside-toplevel

    from mcsc_gui.ui.dialogs.clone_server import CloneServerDialog  # pylint: disable=import-outside-toplevel
    from mcsc_gui.ui.dialogs.delete_server import DeleteServerDialog  # pylint: disable=import-outside-toplevel
    from mcsc_gui.ui.main_window import MainWindow  # pylint: disable=import-outside-toplevel

    manager = ServerManager(tmp_path / "servers", tmp_path / "servers.json",
                            backups_dir=tmp_path / "backups")
    server = manager.register(make_server().config)
    events = ServerEvents(track_registry=False)
    events.attach(server)
    with mock.patch.object(sm, "manager", manager):
        window = MainWindow(events, bridge, native_title_bar=True)
        qtbot.addWidget(window)
        try:
            window.dashboard.edit_server.emit(server.id)
            assert window.navigator.current_route == Route(SERVER_SETTINGS, (server.id,))
            window.navigator.to_dashboard()

            window.dashboard.delete_server.emit(server.id)
            dialogs = window.findChildren(DeleteServerDialog)
            assert len(dialogs) == 1 and dialogs[0].server is server
            dialogs[0].reject()

            window.dashboard.clone_server.emit(server.id)
            dialogs = window.findChildren(CloneServerDialog)
            assert len(dialogs) == 1 and dialogs[0].server is server
            dialog = dialogs[0]
            # The source disappears: the dialog closes
            with qtbot.waitSignal(dialog.closed, timeout=2000):
                events.server_removed.emit(server.id)

            window.dashboard.clone_server.emit("missing")  # ignored
        finally:
            events.close()
