"""System tray icon, closing to the tray, startup prompts in the background, startup settings."""

import json
from pathlib import Path
from unittest import mock

import pytest

from mcsc import ServerState

from mcsc_gui.core import autostart
from mcsc_gui.core import server_manager as sm
from mcsc_gui.core import user_settings as us
from mcsc_gui.core.server_prefs import ServerPrefs
from mcsc_gui.ui.dialogs.app_settings import AppSettingsDialog
from mcsc_gui.ui.tray import TrayIcon, TrayNotifier


def menu_texts(tray):
    tray.rebuild_menu()
    return [a.text() for a in tray.menu.actions()]


def menu_action(tray, text):
    tray.rebuild_menu()
    return next(a for a in tray.menu.actions() if a.text() == text)


@pytest.fixture
def settings_file(monkeypatch, tmp_path: Path) -> Path:
    path = tmp_path / "config" / "user_settings.json"
    monkeypatch.setattr(us, "USER_SETTINGS_PATH", str(path))
    return path


def fake_server(name="Survival", active=True):
    server = mock.Mock(is_active=active)
    server.name = name
    server.state = ServerState.RUNNING if active else ServerState.STOPPED
    return server


# ------------------------------------------------------------------ tray icon


def test_tray_menu_without_running_servers(qtbot):
    with mock.patch.object(sm, "get_servers", lambda: [fake_server(active=False)]):
        tray = TrayIcon()
        texts = menu_texts(tray)
        assert texts[0] == "Open Minecraft Server Creator"
        assert "No servers running" in texts
        assert texts[-1] == "Quit"
        assert not menu_action(tray, "Stop all servers").isEnabled()
        assert tray.icon.toolTip() == "Minecraft Server Creator"


def test_tray_menu_lists_running_servers_and_emits(qtbot):
    servers = [fake_server("Survival"), fake_server("Creative"), fake_server("Off", False)]
    with mock.patch.object(sm, "get_servers", lambda: servers):
        tray = TrayIcon()
        texts = menu_texts(tray)
        assert "Survival · Running" in texts and "Creative · Running" in texts
        assert not any(t.startswith("Off") for t in texts)
        tray.refresh()
        assert "2 servers running" in tray.icon.toolTip()

        for text, signal in (("Open Minecraft Server Creator", tray.open_requested),
                             ("Stop all servers", tray.stop_all_requested),
                             ("Quit", tray.quit_requested)):
            with qtbot.waitSignal(signal, timeout=1000):
                menu_action(tray, text).trigger()


def test_tray_click_opens_the_window(qtbot):
    from PySide6.QtWidgets import QSystemTrayIcon  # pylint: disable=import-outside-toplevel

    with mock.patch.object(sm, "get_servers", lambda: []):
        tray = TrayIcon()
    with qtbot.waitSignal(tray.open_requested, timeout=1000):
        tray.icon.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)


def test_tray_notifier_uses_the_tray_while_hidden(qtbot):
    toasts = mock.Mock()
    tray = mock.Mock()
    visible = {"value": False}
    with mock.patch("mcsc_gui.ui.tray.isValid", lambda _o: True):
        notifier = TrayNotifier(toasts, tray, lambda: visible["value"])
        notifier.error("boom")
        notifier.info("hello")
        qtbot.waitUntil(lambda: tray.notify.called and toasts.info.called, timeout=1000)
        tray.notify.assert_called_once_with("boom", "error")
        visible["value"] = True
        notifier.warning("careful")
        qtbot.waitUntil(lambda: toasts.warning.called, timeout=1000)
    assert tray.notify.call_count == 1


# ---------------------------------------------------------------- main window


@pytest.fixture
def window(qtbot, bridge, tmp_path, settings_file, monkeypatch):
    from mcsc import ServerManager  # pylint: disable=import-outside-toplevel

    from mcsc_gui.ui import main_window as mw  # pylint: disable=import-outside-toplevel
    from mcsc_gui.ui.server_events import ServerEvents  # pylint: disable=import-outside-toplevel

    manager = ServerManager(tmp_path / "servers", tmp_path / "servers.json",
                            backups_dir=tmp_path / "backups")
    events = ServerEvents(track_registry=False)
    with mock.patch.object(sm, "manager", manager), \
            mock.patch.object(sm, "prefs", ServerPrefs(tmp_path / "prefs.json")), \
            mock.patch.object(sm, "_settings", lambda: {}):
        win = mw.MainWindow(events, bridge, native_title_bar=True)
        qtbot.addWidget(win)
        win.quit_calls = []
        monkeypatch.setattr(win, "request_quit", lambda **kw: win.quit_calls.append(kw))
        monkeypatch.setattr(win, "run_startup_prompts", lambda: win.prompts.append(1))
        win.prompts = []
        try:
            yield win
        finally:
            events.close()


def attach_fake_tray(window):
    tray = mock.Mock()
    window.tray = tray
    return tray


def test_close_without_tray_quits(window):
    window.show()
    window.close_by_user()
    assert window.quit_calls == [{"confirm": True}]


def test_close_hides_to_tray_and_hints_once(window, settings_file):
    tray = attach_fake_tray(window)
    window.show()
    window.close_by_user()
    assert not window.isVisible()
    assert window.quit_calls == []
    tray.notify.assert_called_once()
    assert json.loads(settings_file.read_text(encoding="utf-8"))["tray_hint_shown"] is True

    window.bring_to_front()
    assert window.isVisible()
    window.close_by_user()
    assert not window.isVisible()
    tray.notify.assert_called_once()  # the hint is shown only the first time


def test_close_to_tray_can_be_turned_off(window, settings_file):
    attach_fake_tray(window)
    us.UserSettings().update_settings(close_to_tray=False)
    window.show()
    window.close_by_user()
    assert window.quit_calls == [{"confirm": True}]


def test_quit_from_tray_shows_the_window_and_confirms(window):
    attach_fake_tray(window)
    window.quit_from_tray()
    assert window.isVisible()
    assert window.quit_calls == [{"confirm": True}]


def test_attach_tray_wires_signals(qtbot, window):
    with mock.patch.object(sm, "get_servers", lambda: []):
        tray = TrayIcon()
    window.attach_tray(tray)
    tray.open_requested.emit()
    assert window.isVisible()
    tray.quit_requested.emit()
    assert window.quit_calls == [{"confirm": True}]


def test_startup_prompts_wait_for_the_window(qtbot, window, monkeypatch):
    from mcsc_gui.ui import main_window as mw  # pylint: disable=import-outside-toplevel

    monkeypatch.setattr(mw, "STARTUP_PROMPTS_DELAY_MS", 0)
    window.schedule_startup_prompts()  # started in the background: hidden
    qtbot.wait(50)
    assert window.prompts == []
    window.bring_to_front()
    qtbot.waitUntil(lambda: window.prompts == [1], timeout=1000)
    window.hide()
    window.show()
    qtbot.wait(50)
    assert window.prompts == [1]  # only once


def test_update_notice_goes_to_the_tray_while_hidden(window):
    tray = attach_fake_tray(window)
    window._set_update_available(True)  # pylint: disable=protected-access
    tray.notify.assert_called_once_with("Update available")


# ------------------------------------------------------ automatic updates


@pytest.fixture
def updating(window, monkeypatch):
    """The window with a new version out, PyPI faked and _shutdown recorded."""
    from mcsc_gui.ui import main_window as mw  # pylint: disable=import-outside-toplevel

    monkeypatch.setattr(mw, "get_current_version", lambda: "3.2.1")
    claim = mock.Mock(return_value=True)
    monkeypatch.setattr(mw, "claim_auto_update", claim)
    window.shutdowns = []
    monkeypatch.setattr(window, "_shutdown", lambda **kw: window.shutdowns.append(kw))
    window.claim = claim
    return window


def test_update_check_repeats_every_six_hours(updating, monkeypatch):
    from mcsc_gui.ui import main_window as mw  # pylint: disable=import-outside-toplevel

    checks = []
    monkeypatch.setattr(updating, "periodic_update_check", lambda: checks.append(1))
    updating._update_timer.timeout.disconnect()  # pylint: disable=protected-access
    updating._update_timer.timeout.connect(updating.periodic_update_check)  # pylint: disable=protected-access
    updating.start_update_check()
    assert checks == [1]
    assert updating._update_timer.isActive()  # pylint: disable=protected-access
    assert updating._update_timer.interval() == mw.UPDATE_CHECK_INTERVAL_MS == 6 * 3600 * 1000  # pylint: disable=protected-access
    updating._update_timer.timeout.emit()  # pylint: disable=protected-access
    assert checks == [1, 1]


def test_new_version_while_idle_updates_silently_in_the_tray(updating):
    tray = attach_fake_tray(updating)  # window hidden in the tray
    updating._on_latest_version("3.3.0")  # pylint: disable=protected-access
    tray.notify.assert_called_once_with("Update available")
    assert updating.shutdowns == [{"update": True}]
    assert updating._silent_update and updating._update_in_background  # pylint: disable=protected-access
    assert updating.claim.call_args.args[1] == "3.3.0"


def test_silent_update_reopens_with_the_window_if_it_was_open(updating, qtbot):
    updating.show()
    qtbot.waitExposed(updating)
    attach_fake_tray(updating)
    updating._on_latest_version("3.3.0")  # pylint: disable=protected-access
    assert updating.shutdowns == [{"update": True}]
    assert not updating._update_in_background  # pylint: disable=protected-access


def test_running_servers_postpone_the_update_and_notify_once(updating, monkeypatch):
    tray = attach_fake_tray(updating)
    monkeypatch.setattr(sm, "any_server_active", lambda: True)
    updating._on_latest_version("3.3.0")  # pylint: disable=protected-access
    updating._on_latest_version("3.3.0")  # six hours later, still playing
    assert updating.shutdowns == []
    updating.claim.assert_not_called()
    tray.notify.assert_called_once()  # not every six hours

    monkeypatch.setattr(sm, "any_server_active", lambda: False)
    updating._on_latest_version("3.3.0")  # servers stopped: now it updates
    assert updating.shutdowns == [{"update": True}]


def test_no_update_when_up_to_date_offline_or_already_failed(updating):
    attach_fake_tray(updating)
    for latest in (None, "3.2.1", "3.2.0"):
        updating._on_latest_version(latest)  # pylint: disable=protected-access
    updating.claim.assert_not_called()

    updating.claim.return_value = False  # this version already failed once
    updating._on_latest_version("3.3.0")  # pylint: disable=protected-access
    assert updating.shutdowns == []
    assert updating._update_available  # pylint: disable=protected-access  # manual update still offered


def test_open_dialog_postpones_the_update(updating):
    from mcsc_gui.ui.dialogs.update_app import UpdateAppDialog  # pylint: disable=import-outside-toplevel

    updating.show()
    updating.open_dialog(UpdateAppDialog(updating))
    assert not updating.can_update_now()


def test_silent_update_launches_the_updater_without_window(updating, monkeypatch):
    from mcsc_gui.ui import main_window as mw  # pylint: disable=import-outside-toplevel

    launch = mock.Mock(return_value=True)
    monkeypatch.setattr(mw, "launch_updater", launch)
    updating._silent_update, updating._update_in_background = True, True  # pylint: disable=protected-access
    assert updating._launch_updater()  # pylint: disable=protected-access
    launch.assert_called_once_with(silent=True, background=True)


# ------------------------------------------------------------- app settings


@pytest.fixture
def fake_autostart(monkeypatch):
    state = {"enabled": False, "by_user": False, "calls": []}
    monkeypatch.setattr(autostart, "is_supported", lambda: True)
    monkeypatch.setattr(autostart, "is_enabled", lambda: state["enabled"])
    monkeypatch.setattr(autostart, "is_disabled_by_user", lambda: state["by_user"])
    monkeypatch.setattr(autostart, "set_enabled", state["calls"].append)
    return state


def test_app_settings_startup_options(qtbot, host, fake_autostart):
    settings = mock.Mock(user_settings={"close_to_tray": False, "start_with_os": False})
    dialog = AppSettingsDialog(host, user_settings=settings)
    assert dialog.start_with_os is not None and not dialog.start_with_os.isChecked()
    values = dialog.values()
    assert values["start_with_os"] is False
    if dialog.close_to_tray is not None:  # only where a system tray exists
        assert values["close_to_tray"] is False

    dialog.start_with_os.setChecked(True)
    dialog._save(**dialog.values())  # pylint: disable=protected-access
    assert fake_autostart["calls"] == [True]
    assert settings.update_settings.call_args.kwargs["start_with_os"] is True
    dialog._save(**dialog.values())  # unchanged: the entry isn't touched again
    assert fake_autostart["calls"] == [True]


def test_app_settings_start_with_os_is_on_by_default(qtbot, host, fake_autostart):
    settings = mock.Mock(user_settings={})  # setting never saved, entry not created yet
    dialog = AppSettingsDialog(host, user_settings=settings)
    assert dialog.start_with_os.isChecked()
    dialog._save(**dialog.values())  # pylint: disable=protected-access
    assert fake_autostart["calls"] == [True]  # saving creates the missing entry


def test_app_settings_reflects_task_manager(qtbot, host, fake_autostart):
    fake_autostart["by_user"] = True
    dialog = AppSettingsDialog(host, user_settings=mock.Mock(user_settings={}))
    from PySide6.QtWidgets import QLabel  # pylint: disable=import-outside-toplevel

    assert not dialog.start_with_os.isChecked()
    assert any("Task Manager" in w.text() for w in dialog.findChildren(QLabel))


def test_app_settings_hides_startup_where_unsupported(qtbot, host, monkeypatch):
    monkeypatch.setattr(autostart, "is_supported", lambda: False)
    dialog = AppSettingsDialog(host, user_settings=mock.Mock(user_settings={}))
    assert dialog.start_with_os is None
    assert "start_with_os" not in dialog.values()


def test_tray_menu_rebuilt_keeps_only_live_danger_rows(qtbot):
    # Regression: clear() left the deleted "Quit" row registered and painting failed
    with mock.patch.object(sm, "get_servers", lambda: [fake_server()]):
        tray = TrayIcon()
        tray.rebuild_menu()
        tray.rebuild_menu()
    quit_action = next(a for a in tray.menu.actions() if a.text() == "Quit")
    assert tray.menu.danger_item(quit_action) is not None
    assert len(tray.menu._danger_items) == 1  # pylint: disable=protected-access
    tray.menu.grab()  # painting used to raise "already deleted"
