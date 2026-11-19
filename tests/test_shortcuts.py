import platform
import sys
from pathlib import Path

import pytest

from mcsc_gui.core import shortcuts


@pytest.fixture
def linux(monkeypatch, tmp_path: Path):
    """Pretend to be on Linux with desktop/menu/data folders inside tmp_path."""
    monkeypatch.setattr(shortcuts.platform, "system", lambda: "Linux")
    monkeypatch.setattr(shortcuts, "_linux_desktop_dir", lambda: tmp_path / "Desktop")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    monkeypatch.setattr(shortcuts, "user_data_dir", lambda _name: str(tmp_path / "data"))
    monkeypatch.setattr(shortcuts.shutil, "which", lambda _cmd: None)
    return tmp_path


def test_desktop_exec_quoting():
    assert shortcuts._desktop_exec_quote("/usr/bin/python3") == "/usr/bin/python3"
    assert shortcuts._desktop_exec_quote("/opt/my env/python") == '"/opt/my env/python"'
    assert shortcuts._desktop_exec_quote('a"$b') == '"a\\"\\$b"'


def test_launch_command_runs_the_module():
    executable, args = shortcuts.launch_command()
    assert args == ["-m", "mcsc_gui"]
    if platform.system() == "Windows" and Path(sys.executable).with_name("pythonw.exe").exists():
        assert Path(executable).name.lower() == "pythonw.exe"  # no console window


def test_create_linux_shortcuts(linux):
    assert not shortcuts.desktop_shortcut_exists()

    created = shortcuts.create_shortcuts()

    desktop = linux / "Desktop" / "mcsc.desktop"
    menu = linux / "share" / "applications" / "mcsc.desktop"
    assert created == [desktop, menu]
    assert shortcuts.desktop_shortcut_exists()
    entry = desktop.read_text(encoding="utf-8")
    assert "Name=Minecraft Server Creator" in entry
    assert "-m mcsc_gui" in entry
    icon = linux / "data" / "icons" / "logo-512.png"
    assert f"Icon={icon}" in entry
    assert icon.stat().st_size > 0  # copied out of the package


def test_create_only_desktop(linux):
    assert shortcuts.create_shortcuts(menu=False) == [linux / "Desktop" / "mcsc.desktop"]


def test_unsupported_platform(monkeypatch):
    monkeypatch.setattr(shortcuts.platform, "system", lambda: "Darwin")
    assert not shortcuts.is_supported()
    assert not shortcuts.desktop_shortcut_exists()
    with pytest.raises(shortcuts.ShortcutError):
        shortcuts.create_shortcuts()


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows .lnk")
def test_create_windows_lnk(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(shortcuts, "user_data_dir", lambda _name: str(tmp_path / "data"))
    path = tmp_path / "MCSC.lnk"
    shortcuts._create_windows_shortcut(path, shortcuts._install_icon())
    assert path.exists() and path.stat().st_size > 0
