"""Operating system helpers (no UI toolkit)."""

from __future__ import annotations

import logging
import os
import platform
import socket
import subprocess

logger = logging.getLogger(__name__)


def open_file_explorer(path: str | os.PathLike) -> None:
    """Open the system file manager at ``path``."""
    path = os.fspath(path)
    logger.info(f"Opening file explorer at {path}")
    system = platform.system()
    if system == "Windows":
        os.startfile(path)  # pylint: disable=no-member
    elif system == "Darwin":
        subprocess.Popen(["open", path])  # pylint: disable=consider-using-with
    elif system == "Linux":
        subprocess.Popen(["xdg-open", path])  # pylint: disable=consider-using-with
    else:
        logger.warning("Unsupported operating system")


def _has_console() -> bool:
    import ctypes  # pylint: disable=import-outside-toplevel

    return bool(ctypes.windll.kernel32.GetConsoleWindow())


def hide_child_consoles() -> bool:
    """Windows, app started without a console (``pythonw``, desktop shortcut):
    make child processes (java servers, Forge installer) run without opening a
    terminal window of their own.

    pymcsc doesn't pass ``creationflags`` when it spawns java, so every
    ``subprocess.Popen`` (asyncio included) gets ``CREATE_NO_WINDOW`` unless it
    explicitly asks for a new console. Returns True if the patch is active.
    """
    if platform.system() != "Windows" or _has_console():
        return False
    popen_init = subprocess.Popen.__init__
    if getattr(popen_init, "_mcsc_no_window", False):
        return True
    own_console = subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS

    def init(self, *args, **kwargs):
        flags = kwargs.get("creationflags", 0) or 0
        if not flags & own_console:
            kwargs["creationflags"] = flags | subprocess.CREATE_NO_WINDOW
        popen_init(self, *args, **kwargs)

    init._mcsc_no_window = True  # type: ignore[attr-defined]
    subprocess.Popen.__init__ = init  # type: ignore[method-assign]
    logger.info("No console: child processes will run without a window")
    return True


def local_ip_address() -> str | None:
    """This PC's address on the local network (``None`` if there's no network).

    Connecting a UDP socket only picks the outgoing interface: nothing is sent.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            address = sock.getsockname()[0]
    except OSError:
        return None
    return None if address.startswith("0.") else address
