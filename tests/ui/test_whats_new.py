import json
from pathlib import Path
from unittest import mock

import pytest
from PySide6.QtWidgets import QLabel

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core import user_settings as us
from mcsc_gui.core.changelog import parse_changelog
from mcsc_gui.core.server_prefs import ServerPrefs
from mcsc_gui.ui.dialogs import whats_new as wn
from mcsc_gui.ui.dialogs.app_settings import AppSettingsDialog
from mcsc_gui.ui.dialogs.whats_new import WhatsNewDialog

NOTES = parse_changelog({"releases": [
    {"version": v, "date": "2026-11-21",
     "highlights": {"en": [f"New in {v}"], "it": [f"Novità {v}"]}}
    for v in ("3.0.0", "3.0.1", "3.1.0", "3.2.0")
]})


@pytest.fixture
def settings_file(monkeypatch, tmp_path: Path) -> Path:
    path = tmp_path / "config" / "user_settings.json"
    monkeypatch.setattr(us, "USER_SETTINGS_PATH", str(path))
    return path


def make_settings(settings_file: Path, data: dict | None) -> us.UserSettings:
    if data is not None:
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        settings_file.write_text(json.dumps(data), encoding="utf-8")
    return us.UserSettings()


def saved(settings_file: Path):
    return json.loads(settings_file.read_text(encoding="utf-8")).get(wn.SETTING)


def versions(notes):
    return [n.version for n in notes]


# ------------------------------------------------------------ startup logic


def test_upgrade_shows_the_new_version(settings_file):
    settings = make_settings(settings_file, {wn.SETTING: "3.0.1"})
    assert versions(wn.startup_notes(settings, "3.1.0", NOTES)) == ["3.1.0"]


def test_skipped_versions_are_all_listed(settings_file):
    settings = make_settings(settings_file, {wn.SETTING: "3.0.0"})
    assert versions(wn.startup_notes(settings, "3.2.0", NOTES)) == ["3.2.0", "3.1.0", "3.0.1"]


def test_shown_only_once(settings_file):
    settings = make_settings(settings_file, {wn.SETTING: "3.0.1"})
    wn.mark_seen(settings, "3.1.0")
    assert saved(settings_file) == "3.1.0"
    assert wn.startup_notes(us.UserSettings(), "3.1.0", NOTES) == []


def test_fresh_install_shows_nothing(settings_file):
    settings = make_settings(settings_file, None)
    assert wn.startup_notes(settings, "3.1.0", NOTES) == []
    wn.mark_seen(settings, "3.1.0")
    assert saved(settings_file) == "3.1.0"


def test_upgrade_from_a_version_without_the_feature(settings_file):
    settings = make_settings(settings_file, {"shortcut_prompt_shown": True})
    assert versions(wn.startup_notes(settings, "3.1.0", NOTES)) == ["3.1.0"]
    # Servers also tell an existing user from a new one
    settings = make_settings(settings_file, {})
    assert versions(wn.startup_notes(settings, "3.1.0", NOTES, has_servers=True)) == ["3.1.0"]


@pytest.mark.parametrize("last, current", [
    ("3.0.1", "3.0.2"),   # no notes for this version
    ("3.2.0", "3.1.0"),   # downgrade
    ("3.0.1", "0.0.0"),   # development version
    ("3.0.1", "dev"),
])
def test_nothing_to_show(settings_file, last, current):
    settings = make_settings(settings_file, {wn.SETTING: last})
    assert wn.startup_notes(settings, current, NOTES) == []


def test_development_version_is_never_saved(settings_file):
    settings = make_settings(settings_file, {wn.SETTING: "3.0.1"})
    wn.mark_seen(settings, "0.0.0")
    assert saved(settings_file) == "3.0.1"


# ----------------------------------------------------------------- dialog


def dialog_texts(dialog) -> list[str]:
    return [lbl.text() for lbl in dialog.findChildren(QLabel)]


def test_dialog_lists_the_notes_in_the_language(qtbot, host):
    dialog = WhatsNewDialog(host, NOTES[:2], language="it")
    dialog.open()
    texts = dialog_texts(dialog)
    assert "Novità 3.2.0" in texts and "Novità 3.1.0" in texts
    assert "Novità 3.0.1" not in texts
    assert dialog.scroll is not None and dialog.empty_label is None
    assert dialog.scroll.height() <= host.height() * wn.MAX_HEIGHT_RATIO + 1


def test_dialog_falls_back_to_english(qtbot, host):
    notes = parse_changelog({"releases": [
        {"version": "3.1.0", "highlights": {"en": ["Only English"]}}]})
    dialog = WhatsNewDialog(host, notes, language="it")
    dialog.open()
    assert "Only English" in dialog_texts(dialog)


def test_dialog_empty_state(qtbot, host):
    dialog = WhatsNewDialog(host, [])
    dialog.open()
    assert dialog.scroll is None and dialog.empty_label is not None
    with qtbot.waitSignal(dialog.closed, timeout=2000):
        dialog.ok_button.click()
    assert dialog.result is True


def test_long_notes_scroll(qtbot, host):
    notes = parse_changelog({"releases": [
        {"version": f"3.{i}.0", "highlights": {"en": [f"Change {j}" for j in range(8)]}}
        for i in range(15)]})
    dialog = WhatsNewDialog(host, notes)
    dialog.open()
    assert dialog.scroll.verticalScrollBar().maximum() > 0


# -------------------------------------------------------- settings button


def test_settings_changelog_button(qtbot, host, settings_file):
    settings = make_settings(settings_file, {"language": "en"})
    dialog = AppSettingsDialog(host, settings)
    dialog.open()
    dialog.native_title_bar.setChecked(not dialog.native_title_bar.isChecked())  # unsaved
    with qtbot.waitSignals([dialog.changelog_requested, dialog.closed], timeout=2000):
        dialog.changelog_button.click()
    assert dialog.result is False
    assert json.loads(settings_file.read_text(encoding="utf-8")) == {"language": "en"}


# ------------------------------------------------------------ main window


@pytest.fixture
def window(qtbot, bridge, tmp_path, settings_file, monkeypatch):
    from mcsc import ServerManager  # pylint: disable=import-outside-toplevel

    from mcsc_gui.ui import main_window as mw  # pylint: disable=import-outside-toplevel
    from mcsc_gui.ui.server_events import ServerEvents  # pylint: disable=import-outside-toplevel

    events_sent = []

    async def fake_event(name, details=None):
        events_sent.append((name, details))

    monkeypatch.setattr(mw, "send_event_async", fake_event)
    monkeypatch.setattr(mw, "load_changelog", lambda: list(NOTES))
    monkeypatch.setattr(mw, "get_current_version", lambda: "3.1.0")
    manager = ServerManager(tmp_path / "servers", tmp_path / "servers.json",
                            backups_dir=tmp_path / "backups")
    events = ServerEvents(track_registry=False)
    with mock.patch.object(sm, "manager", manager), \
            mock.patch.object(sm, "prefs", ServerPrefs(tmp_path / "prefs.json")), \
            mock.patch.object(sm, "_settings", lambda: {}):
        win = mw.MainWindow(events, bridge, native_title_bar=True)
        qtbot.addWidget(win)
        shortcut_prompts = []
        monkeypatch.setattr(win, "maybe_prompt_shortcut", lambda: shortcut_prompts.append(1))
        win.events_sent = events_sent
        win.shortcut_prompts = shortcut_prompts
        try:
            yield win
        finally:
            events.close()


def test_startup_after_update_shows_whats_new_only(qtbot, window, settings_file):
    make_settings(settings_file, {wn.SETTING: "3.0.1"})
    window.run_startup_prompts()
    dialogs = window.findChildren(WhatsNewDialog)
    assert len(dialogs) == 1 and versions(dialogs[0].notes) == ["3.1.0"]
    assert window.shortcut_prompts == []
    assert saved(settings_file) == "3.1.0"  # saved as soon as it's shown
    qtbot.waitUntil(lambda: bool(window.events_sent), timeout=2000)
    assert window.events_sent == [("whats_new_shown", {"source": "startup", "version": "3.1.0"})]

    dialogs[0].accept()
    qtbot.waitUntil(lambda: not window.findChildren(WhatsNewDialog), timeout=2000)
    window.run_startup_prompts()  # next launch
    assert not window.findChildren(WhatsNewDialog)


def test_first_launch_shows_the_shortcut_prompt(window, settings_file):
    window.run_startup_prompts()
    assert not window.findChildren(WhatsNewDialog)
    assert window.shortcut_prompts == [1]
    assert saved(settings_file) == "3.1.0"


def test_changelog_from_the_settings(qtbot, window, settings_file):
    make_settings(settings_file, {wn.SETTING: "3.1.0"})
    window.open_settings_dialog()
    settings_dialog = window.findChildren(AppSettingsDialog)[0]
    settings_dialog.changelog_button.click()
    dialogs = window.findChildren(WhatsNewDialog)
    assert len(dialogs) == 1 and versions(dialogs[0].notes) == versions(NOTES)
    qtbot.waitUntil(lambda: not window.findChildren(AppSettingsDialog), timeout=2000)
    qtbot.waitUntil(lambda: bool(window.events_sent), timeout=2000)
    assert window.events_sent[0][1]["source"] == "settings"
