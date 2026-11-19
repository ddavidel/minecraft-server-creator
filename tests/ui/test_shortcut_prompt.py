import json
from pathlib import Path

import pytest

from mcsc_gui.core import shortcuts
from mcsc_gui.core import user_settings as us
from mcsc_gui.ui.dialogs import shortcut as prompt
from mcsc_gui.ui.dialogs.app_settings import AppSettingsDialog
from mcsc_gui.ui.dialogs.shortcut import ShortcutPromptDialog


@pytest.fixture
def settings_file(monkeypatch, tmp_path: Path) -> Path:
    path = tmp_path / "config" / "user_settings.json"
    monkeypatch.setattr(us, "USER_SETTINGS_PATH", str(path))
    return path


@pytest.fixture
def fake_shortcuts(monkeypatch):
    state = {"exists": False, "created": 0}
    monkeypatch.setattr(shortcuts, "is_supported", lambda: True)
    monkeypatch.setattr(shortcuts, "desktop_shortcut_exists", lambda: state["exists"])

    def create(**_kwargs):
        state["created"] += 1
        state["exists"] = True
        return []

    monkeypatch.setattr(shortcuts, "create_shortcuts", create)
    return state


def saved_flag(path: Path):
    return json.loads(path.read_text(encoding="utf-8")).get(prompt.PROMPT_SETTING)


def test_prompt_only_once(settings_file, fake_shortcuts):
    settings = us.UserSettings()
    assert prompt.should_prompt(settings)
    prompt.mark_prompt_shown(settings)
    assert saved_flag(settings_file) is True

    # Even if the shortcut is deleted later, the prompt doesn't come back
    fake_shortcuts["exists"] = False
    assert not prompt.should_prompt(us.UserSettings())


def test_no_prompt_when_shortcut_exists(settings_file, fake_shortcuts):
    fake_shortcuts["exists"] = True
    assert not prompt.should_prompt(us.UserSettings())
    assert saved_flag(settings_file) is True  # remembered: deleting it won't trigger the prompt


def test_no_prompt_on_unsupported_os(settings_file, monkeypatch):
    monkeypatch.setattr(shortcuts, "is_supported", lambda: False)
    assert not prompt.should_prompt(us.UserSettings())


def test_prompt_yes_creates_shortcuts(qtbot, host, bridge, settings_file, fake_shortcuts):
    dialog = ShortcutPromptDialog(host, us.UserSettings())
    dialog.open()
    dialog.confirm_button.click()
    qtbot.waitUntil(lambda: fake_shortcuts["created"] == 1, timeout=2000)
    qtbot.waitUntil(lambda: settings_file.exists() and saved_flag(settings_file), timeout=2000)


def test_prompt_no_creates_nothing(qtbot, host, bridge, settings_file, fake_shortcuts):
    dialog = ShortcutPromptDialog(host, us.UserSettings())
    dialog.open()
    dialog.cancel_button.click()
    qtbot.wait(100)
    assert fake_shortcuts["created"] == 0


def test_settings_button_creates_shortcuts(qtbot, host, bridge, settings_file, fake_shortcuts):
    settings = us.UserSettings()
    dialog = AppSettingsDialog(host, settings)
    dialog.open()
    assert dialog.shortcut_button is not None
    dialog.shortcut_button.click()
    qtbot.waitUntil(lambda: fake_shortcuts["created"] == 1, timeout=2000)
    qtbot.waitUntil(lambda: settings.user_settings.get(prompt.PROMPT_SETTING) is True,
                    timeout=2000)
