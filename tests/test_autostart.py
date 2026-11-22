"""Login autostart entry: Windows registry (simulated) and Linux XDG autostart."""

from pathlib import Path

import pytest

from mcsc_gui.core import autostart
from mcsc_gui.core import shortcuts
from mcsc_gui.core import user_settings as us

PYTHONW = r"C:\Program Files\MCSC\python\pythonw.exe"


class FakeWinreg:
    """The subset of ``winreg`` used by autostart, backed by a dict."""

    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 2
    REG_SZ = 1
    REG_BINARY = 3

    def __init__(self):
        self.keys: dict[str, dict[str, object]] = {}

    class _Key:
        def __init__(self, values):
            self.values = values

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    def OpenKey(self, _root, path, _reserved=0, _access=0):  # noqa: N802
        if path not in self.keys:
            raise FileNotFoundError(path)
        return self._Key(self.keys[path])

    def CreateKeyEx(self, _root, path, _reserved=0, _access=0):  # noqa: N802
        return self._Key(self.keys.setdefault(path, {}))

    def QueryValueEx(self, key, name):  # noqa: N802
        if name not in key.values:
            raise FileNotFoundError(name)
        return key.values[name], self.REG_SZ

    def SetValueEx(self, key, name, _reserved, _type, value):  # noqa: N802
        key.values[name] = value

    def DeleteValue(self, key, name):  # noqa: N802
        if name not in key.values:
            raise FileNotFoundError(name)
        del key.values[name]

    def run_value(self):
        return self.keys.get(autostart.RUN_KEY, {}).get(autostart.VALUE_NAME)

    def approved_value(self):
        return self.keys.get(autostart.APPROVED_KEY, {}).get(autostart.VALUE_NAME)

    def disable_from_task_manager(self):
        self.keys.setdefault(autostart.APPROVED_KEY, {})[autostart.VALUE_NAME] = \
            bytes([0x03]) + bytes(11)


@pytest.fixture
def launcher(monkeypatch):
    state = {"exe": PYTHONW}
    monkeypatch.setattr(shortcuts, "launch_command", lambda: (state["exe"], ["-m", "mcsc_gui"]))
    monkeypatch.delenv(autostart.DISABLE_ENV, raising=False)
    monkeypatch.setattr(autostart, "default_disabled", lambda: False)
    return state


@pytest.fixture
def windows(monkeypatch, launcher):
    reg = FakeWinreg()
    monkeypatch.setattr(autostart.platform, "system", lambda: "Windows")
    monkeypatch.setattr(autostart, "_winreg", lambda: reg)
    return reg


@pytest.fixture
def linux(monkeypatch, tmp_path, launcher):
    monkeypatch.setattr(autostart.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path / "config" / "autostart" / autostart.LINUX_AUTOSTART_FILE


@pytest.fixture
def settings(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(us, "USER_SETTINGS_PATH", str(tmp_path / "user_settings.json"))
    return us.UserSettings()


def test_command_starts_in_background(launcher):
    assert autostart.command() == f'"{PYTHONW}" -m mcsc_gui --background'


def test_windows_enable_disable(windows):
    assert not autostart.is_enabled()
    autostart.enable()
    assert windows.run_value() == autostart.command()
    assert autostart.is_enabled() and autostart.is_up_to_date()
    autostart.disable()
    assert windows.run_value() is None
    assert not autostart.is_enabled()
    autostart.disable()  # nothing to remove: no error


def test_windows_task_manager_choice_is_read_and_cleared_on_enable(windows):
    autostart.enable()
    windows.disable_from_task_manager()
    assert autostart.is_registered()
    assert autostart.is_disabled_by_user()
    assert not autostart.is_enabled()

    autostart.enable()  # the user turned it back on from the app
    assert windows.approved_value()[0] == 0x02
    assert autostart.is_enabled()

    autostart.disable()
    assert windows.approved_value() is None


def test_sync_first_run_enables_by_default(windows, settings):
    autostart.sync(settings)
    assert settings.user_settings["start_with_os"] is True
    assert windows.run_value() == autostart.command()


def test_sync_first_run_respects_dev_opt_out(windows, settings, monkeypatch):
    monkeypatch.setattr(autostart, "default_disabled", lambda: True)
    autostart.sync(settings)
    assert "start_with_os" not in settings.user_settings  # the installed app still decides
    assert windows.run_value() is None


def test_default_disabled_env(monkeypatch):
    monkeypatch.setenv(autostart.DISABLE_ENV, "1")
    assert autostart.default_disabled()


def test_sync_refreshes_a_moved_install(windows, settings, launcher):
    autostart.sync(settings)
    launcher["exe"] = r"D:\Apps\MCSC\python\pythonw.exe"
    assert not autostart.is_up_to_date()
    autostart.sync(settings)
    assert windows.run_value() == autostart.command()
    assert "D:\\Apps" in windows.run_value()


def test_sync_never_overrides_task_manager(windows, settings, launcher):
    autostart.sync(settings)
    windows.disable_from_task_manager()
    launcher["exe"] = r"D:\Apps\MCSC\python\pythonw.exe"
    autostart.sync(settings)
    assert autostart.is_disabled_by_user()
    assert "D:\\Apps" not in windows.run_value()


def test_sync_when_turned_off_does_nothing(windows, settings):
    settings.update_settings(start_with_os=False)
    autostart.sync(settings)
    assert windows.run_value() is None


def test_linux_autostart_file(linux):
    autostart.enable()
    text = linux.read_text(encoding="utf-8")
    assert "Exec=" in text and "--background" in text
    assert autostart.is_enabled() and autostart.is_up_to_date()
    linux.write_text(text + "Hidden=true\n", encoding="utf-8")
    assert autostart.is_disabled_by_user()
    autostart.disable()
    assert not linux.exists()


def test_unsupported_platform(monkeypatch, settings):
    monkeypatch.setattr(autostart.platform, "system", lambda: "Darwin")
    assert not autostart.is_supported()
    assert not autostart.is_enabled()
    autostart.sync(settings)  # no-op
    assert "start_with_os" not in settings.user_settings
    with pytest.raises(autostart.AutostartError):
        autostart.enable()
