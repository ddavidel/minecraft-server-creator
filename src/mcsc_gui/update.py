"""
Update module for MCSC
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from importlib.metadata import version
from collections.abc import Callable
from pathlib import Path, PureWindowsPath

import requests
from packaging.version import InvalidVersion, Version

from mcsc_gui.config.settings import (
    DEFAULT_LANGUAGE,
    LOG_DIR_PATH,
    PACKAGE_NAME,
    PYPI_PACKAGE_URL,
)

logger = logging.getLogger(__name__)


def get_current_version() -> str:
    """
    Get current version
    """
    try:
        current = version(PACKAGE_NAME)
    except Exception:  # pylint: disable=broad-exception-caught
        current = "0.0.0"

    logger.info(f"Currently running verion {current}")
    return current


def is_newer(latest: str, current: str) -> bool:
    """True if ``latest`` is a later version than ``current`` (PEP 440: 3.2.10 > 3.2.9).

    A pre-release (``4.0.0rc1``) is never offered: pip wouldn't install it.
    """
    try:
        latest_version, current_version = Version(latest), Version(current)
    except InvalidVersion:
        return False
    return not latest_version.is_prerelease and latest_version > current_version


def get_latest_version(timeout: float = 5) -> str | None:
    """The latest version published on PyPI (None if PyPI doesn't answer)."""
    response = requests.get(PYPI_PACKAGE_URL, timeout=timeout)
    if response.status_code != 200:
        logger.warning(f"Unable to check for updates (HTTP {response.status_code})")
        return None
    return str(response.json()["info"]["version"])


def check_for_updates() -> bool:
    """
    Check for updates
    """
    logger.info("Checking for updates...")
    latest = get_latest_version()
    return latest is not None and is_newer(latest, get_current_version())


# Update workflow: the app can't upgrade itself while it's running, because
# Windows locks the files it has open (the ``mcsc.exe`` launcher, Qt's DLLs...).
# It starts the standalone updater (:mod:`mcsc_gui.updater`) and quits; the
# updater waits for it to exit, runs pip and reopens the app.

UPDATER_DIR = os.path.join(tempfile.gettempdir(), "mcsc-updater")


def _windowless_python() -> str:
    """``pythonw.exe`` next to the current interpreter (no console window), if any."""
    if sys.platform == "win32":
        candidate = Path(sys.executable).with_name("pythonw.exe")
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _console_python() -> str:
    """``python.exe`` (not ``pythonw.exe``): pip's output must be readable."""
    if sys.platform == "win32":
        candidate = Path(sys.executable).with_name("python.exe")
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _process_image(pid: int) -> str | None:
    """Full path of the executable of a process (Windows only)."""
    if sys.platform != "win32":
        return None
    import ctypes  # pylint: disable=import-outside-toplevel
    from ctypes import wintypes  # pylint: disable=import-outside-toplevel

    kernel32 = ctypes.windll.kernel32
    query_limited_information = 0x1000
    handle = kernel32.OpenProcess(query_limited_information, False, pid)
    if not handle:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return None
    finally:
        kernel32.CloseHandle(handle)


def _parent_pids() -> dict[int, int]:
    """PID -> parent PID of every process (Windows only)."""
    if sys.platform != "win32":
        return {}
    import ctypes  # pylint: disable=import-outside-toplevel
    from ctypes import wintypes  # pylint: disable=import-outside-toplevel

    class ProcessEntry(ctypes.Structure):  # PROCESSENTRY32W
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        return {}
    parents: dict[int, int] = {}
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(ProcessEntry)
        ok = kernel32.Process32FirstW(wintypes.HANDLE(snapshot), ctypes.byref(entry))
        while ok:
            parents[entry.th32ProcessID] = entry.th32ParentProcessID
            ok = kernel32.Process32NextW(wintypes.HANDLE(snapshot), ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(wintypes.HANDLE(snapshot))
    return parents


def launcher_pid(pid: int | None = None, parents: dict[int, int] | None = None,
                 image: Callable[[int], str | None] | None = None) -> int | None:
    """PID of the ``mcsc.exe`` launcher that started this process, if any.

    pip's console-script launcher runs Python as a child process and exits
    with it: the updater must wait for it too, or pip can't replace
    ``mcsc.exe``. In a venv the chain is ``mcsc.exe`` -> ``python.exe`` (the
    venv redirector) -> the real interpreter, so the redirectors are skipped.
    """
    pid = os.getpid() if pid is None else pid
    parents = _parent_pids() if parents is None else parents
    image = image or _process_image
    for _ in range(4):
        pid = parents.get(pid, 0)
        if pid <= 0:
            return None
        path = image(pid)
        if not path:
            return None
        # Windows-only chain: parse as a Windows path on every OS (tests run on Linux too)
        stem = PureWindowsPath(path).stem.lower()
        if stem == "mcsc":
            return pid
        if stem not in ("python", "pythonw"):
            return None
    return None


def relaunch_command(argv: list[str] | None = None, background: bool | None = None) -> list[str]:
    """Command that reopens the app, keeping its options (e.g. ``--debug``).

    ``background`` True/False adds/removes ``--background`` (tray only, no
    window); None keeps what the app was started with.
    """
    from mcsc_gui.core.autostart import BACKGROUND_ARG  # pylint: disable=import-outside-toplevel

    argv = list(sys.argv if argv is None else argv)
    options = [arg for arg in argv[1:] if arg.startswith("--")]
    if background is not None:
        options = [arg for arg in options if arg != BACKGROUND_ARG]
        if background:
            options.append(BACKGROUND_ARG)
    script = Path(argv[0]) if argv else Path()
    # Started from a script of the source tree (scripts/start.py): rerun it
    if script.suffix == ".py" and script.name != "__main__.py" and script.exists():
        return [_windowless_python(), str(script.resolve()), *options]
    return [_windowless_python(), "-m", "mcsc_gui", *options]


def updater_command(script: str, *, pid: int, launcher: int | None, lang: str,
                    icon: str | None, log: str | None,
                    relaunch: list[str], silent: bool = False) -> list[str]:
    command = [_windowless_python(), "-I", script,
               "--python", _console_python(), "--package", PACKAGE_NAME,
               "--wait-pid", str(pid), "--relaunch", json.dumps(relaunch), "--lang", lang]
    if launcher:
        command += ["--wait-pid", str(launcher)]
    if icon:
        command += ["--icon", icon]
    if log:
        command += ["--log", log]
    if silent:
        command.append("--silent")
    return command


def launch_updater(silent: bool = False, background: bool | None = None) -> bool:
    """Start the updater process (it waits for this app to exit). Returns success.

    ``silent``: no updater window; the app reopens by itself once pip is done
    (also when pip fails, on the version already installed). ``background``:
    see :func:`relaunch_command`.
    """
    try:
        os.makedirs(UPDATER_DIR, exist_ok=True)
        # Run a copy: pip replaces the package files while the updater runs
        script = os.path.join(UPDATER_DIR, "mcsc_updater.py")
        shutil.copyfile(Path(__file__).with_name("updater.py"), script)
        icon = None
        source_icon = Path(__file__).parent / "static" / "logo.ico"
        if source_icon.exists():
            icon = os.path.join(UPDATER_DIR, "logo.ico")
            shutil.copyfile(source_icon, icon)
        os.makedirs(LOG_DIR_PATH, exist_ok=True)
        command = updater_command(
            script, pid=os.getpid(), launcher=launcher_pid(), lang=DEFAULT_LANGUAGE,
            icon=icon, log=os.path.join(LOG_DIR_PATH, "updater.log"),
            relaunch=relaunch_command(background=background), silent=silent,
        )
        logger.info(f"Starting the updater: {command}")
        _spawn_detached(command)
        return True
    except OSError:
        logger.exception("Can't start the updater")
        return False


def _spawn_detached(command: list[str]) -> None:
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL, "cwd": UPDATER_DIR, "close_fds": True}
    if sys.platform != "win32":
        subprocess.Popen(command, start_new_session=True, **kwargs)  # pylint: disable=consider-using-with
        return
    flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
             | subprocess.CREATE_NO_WINDOW)
    try:
        # Leave the launcher's job object, or the updater dies together with the app
        subprocess.Popen(command, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB,  # pylint: disable=consider-using-with
                         **kwargs)
    except OSError:
        subprocess.Popen(command, creationflags=flags, **kwargs)  # pylint: disable=consider-using-with


# Automatic updates (always on, they can't be turned off). At startup, before
# the window and the servers, the app checks PyPI and, if there's a new
# version, starts the updater in silent mode and exits: the updater reopens it
# with the same options (``--background`` included), so it opens as it would
# have, window or tray only. While the app runs it checks again every few
# hours and updates the same way as soon as no server is running (see
# MainWindow.periodic_update_check).

AUTO_UPDATE_TIMEOUT = 3  # seconds: the window waits for this check


def installed_as_package(module_file: str | None = None) -> bool:
    """True if the app runs from an installed package (not a source checkout).

    pip would replace an editable install with the PyPI release.
    """
    parts = {part.lower() for part in Path(module_file or __file__).resolve().parts}
    return bool(parts & {"site-packages", "dist-packages"})


def auto_update_at_startup(settings, *, latest_version: Callable[[], str | None] | None = None,
                           launch: Callable[..., bool] | None = None) -> bool:
    """Start the silent updater if a new version is out. True: the app must exit now.

    ``settings`` is a :class:`~mcsc_gui.core.user_settings.UserSettings`.
    Never raises: any problem just means "no update now".
    """
    try:
        latest = (latest_version or (lambda: get_latest_version(AUTO_UPDATE_TIMEOUT)))()
        if not claim_auto_update(settings, latest):
            return False
        return (launch or launch_updater)(silent=True)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning(f"Automatic update skipped: {e}")
        return False


def claim_auto_update(settings, latest: str | None) -> bool:
    """True if the app should update itself to ``latest`` now; records the attempt.

    A version is tried once: if the app is still on an older one afterwards,
    the update failed and the user updates by hand (no update loop).
    """
    if latest is None or not is_newer(latest, get_current_version()):
        return False
    if not installed_as_package():
        logger.info("Automatic update skipped: not running from an installed package")
        return False
    if settings.user_settings.get("auto_update_attempted") == latest:
        logger.warning(f"The automatic update to {latest} already failed: not retrying")
        return False
    logger.info(f"Version {latest} available: updating automatically")
    settings.update_settings(auto_update_attempted=latest)
    return True
