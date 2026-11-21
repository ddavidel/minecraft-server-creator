"""
Start the app when the user logs in (Windows registry ``Run`` key, Linux XDG autostart).

The app owns the entry: it creates it, keeps its command up to date (the
install folder may change) and removes it. On Windows the user can also turn
it off from Task Manager (``StartupApproved``): that choice is respected and
never overridden automatically. The installer only removes the entry on
uninstall. macOS is not supported.

The entry starts the app with :data:`BACKGROUND_ARG`: no window, only the tray icon.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

from mcsc_gui.core import shortcuts

logger = logging.getLogger(__name__)

BACKGROUND_ARG = "--background"
SETTING = "start_with_os"
DEFAULT_ENABLED = True
# Set to skip the default registration (development checkouts, tests)
DISABLE_ENV = "MCSC_NO_AUTOSTART"

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
VALUE_NAME = "MinecraftServerCreator"
LINUX_AUTOSTART_FILE = "mcsc.desktop"

# StartupApproved: 12 bytes, the first one tells whether the entry is enabled.
# Task Manager writes 0x03 (or 0x07) when the user disables it.
_APPROVED_ENABLED = bytes([0x02]) + bytes(11)
_DISABLED_FLAGS = {0x01, 0x03, 0x07}


class AutostartError(RuntimeError):
    """The autostart entry couldn't be changed."""


def is_supported() -> bool:
    return platform.system() in {"Windows", "Linux"}


def command_args() -> list[str]:
    """Executable + arguments of the autostart entry."""
    executable, args = shortcuts.launch_command()
    return [executable, *args, BACKGROUND_ARG]


def command() -> str:
    """The Windows command line of the autostart entry."""
    return subprocess.list2cmdline(command_args())


def default_disabled() -> bool:
    """True when the default (enabled) must not be applied: dev runs, tests."""
    from mcsc_gui.config import settings as mcssettings  # pylint: disable=import-outside-toplevel

    flag = os.environ.get(DISABLE_ENV, "").strip().lower() in {"1", "true", "yes"}
    return flag or bool(mcssettings.DEBUG)


# --------------------------------------------------------------- Windows

def _winreg():
    import winreg  # pylint: disable=import-outside-toplevel,import-error

    return winreg


def _read_value(key_path: str) -> Any:
    winreg = _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            return winreg.QueryValueEx(key, VALUE_NAME)[0]
    except FileNotFoundError:
        return None


def _delete_value(key_path: str) -> None:
    winreg = _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        pass


def _windows_entry() -> str | None:
    value = _read_value(RUN_KEY)
    return value if isinstance(value, str) and value else None


def _windows_disabled_by_user() -> bool:
    value = _read_value(APPROVED_KEY)
    return isinstance(value, (bytes, bytearray)) and len(value) > 0 \
        and value[0] in _DISABLED_FLAGS


def _windows_enable() -> None:
    winreg = _winreg()
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
    # The user chose to turn it on: clear a "disabled" left by Task Manager
    if _windows_disabled_by_user():
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, APPROVED_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_BINARY, _APPROVED_ENABLED)


def _windows_disable() -> None:
    _delete_value(RUN_KEY)
    _delete_value(APPROVED_KEY)


# ----------------------------------------------------------------- Linux

def linux_autostart_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(config_home) / "autostart" / LINUX_AUTOSTART_FILE


def linux_entry() -> str:
    """The autostart ``.desktop`` file: the app shortcut started in the background."""
    exec_line = " ".join(shortcuts._desktop_exec_quote(a)  # pylint: disable=protected-access
                         for a in command_args()).replace("%", "%%")
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={shortcuts.SHORTCUT_NAME}\n"
        f"Comment={shortcuts.SHORTCUT_COMMENT}\n"
        f"Exec={exec_line}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def _linux_entry_on_disk() -> str | None:
    try:
        return linux_autostart_path().read_text(encoding="utf-8")
    except OSError:
        return None


def _linux_disabled_by_user() -> bool:
    text = _linux_entry_on_disk() or ""
    return any(line.strip().lower() in {"hidden=true", "x-gnome-autostart-enabled=false"}
               for line in text.splitlines())


# ------------------------------------------------------------------- API

def is_registered() -> bool:
    """An autostart entry exists (enabled or not)."""
    system = platform.system()
    if system == "Windows":
        return _windows_entry() is not None
    if system == "Linux":
        return linux_autostart_path().exists()
    return False


def is_disabled_by_user() -> bool:
    """The entry exists but the user turned it off outside the app (Task Manager)."""
    system = platform.system()
    if system == "Windows":
        return _windows_entry() is not None and _windows_disabled_by_user()
    if system == "Linux":
        return _linux_disabled_by_user()
    return False


def is_enabled() -> bool:
    """The app actually starts at login."""
    try:
        return is_registered() and not is_disabled_by_user()
    except OSError as e:
        logger.warning(f"Can't read the autostart entry: {e}")
        return False


def is_up_to_date() -> bool:
    """The entry starts this installation (same executable and arguments)."""
    system = platform.system()
    if system == "Windows":
        return _windows_entry() == command()
    if system == "Linux":
        return _linux_entry_on_disk() == linux_entry()
    return True


def enable() -> None:
    """Create (or refresh) the autostart entry, enabled."""
    if not is_supported():
        raise AutostartError(f"Autostart is not supported on {platform.system()}")
    try:
        if platform.system() == "Windows":
            _windows_enable()
        else:
            path = linux_autostart_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(linux_entry(), encoding="utf-8")
    except OSError as e:
        raise AutostartError(f"Can't enable autostart: {e}") from e
    logger.info("Autostart enabled")


def disable() -> None:
    """Remove the autostart entry (no error if there's none)."""
    if not is_supported():
        return
    try:
        if platform.system() == "Windows":
            _windows_disable()
        else:
            linux_autostart_path().unlink(missing_ok=True)
    except OSError as e:
        raise AutostartError(f"Can't disable autostart: {e}") from e
    logger.info("Autostart disabled")


def set_enabled(enabled: bool) -> None:
    if enabled:
        enable()
    else:
        disable()


def sync(settings) -> None:
    """Align the OS entry with the ``start_with_os`` setting at startup.

    * setting missing (first run of this version): apply the default (enabled);
      with :func:`default_disabled` nothing is done or saved, so a development
      run never changes the choice of the installed app (same settings file);
    * enabled: refresh the entry if it points to another installation, but
      never re-enable an entry the user turned off from Task Manager;
    * disabled: nothing (the entry is removed when the user saves the setting).
    """
    if not is_supported():
        return
    values = settings.user_settings
    if SETTING not in values:
        if default_disabled():
            logger.info("Autostart default skipped (development run)")
            return
        settings.update_settings(**{SETTING: DEFAULT_ENABLED})
        if DEFAULT_ENABLED:
            enable()
        return
    if not values.get(SETTING):
        return
    if is_disabled_by_user():
        logger.info("Autostart turned off by the user outside the app: left as is")
        return
    if not is_registered() or not is_up_to_date():
        enable()
