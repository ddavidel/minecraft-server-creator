"""
App session: the ``app_close`` telemetry event, unclean exits and OS shutdown.

Living in the tray, the app is often still running when the user shuts the PC
down: Windows ends the process right after ``WM_ENDSESSION`` and the normal quit
path never runs. These helpers (no UI toolkit) let the session end handler
(:mod:`mcsc_gui.ui.session_end`) delay the shutdown and close cleanly.

- :func:`begin` / :func:`end` keep a marker file while the app runs: a marker
  found at start means the previous run was killed (power loss, Task Manager).
- :func:`send_app_close` sends ``app_close`` once per run, queued on disk first.
- :class:`ShutdownBlocker` asks Windows to wait (``ShutdownBlockReasonCreate``)
  while servers run, showing the reason in the "apps preventing shutdown" screen.
"""

from __future__ import annotations

import logging
import os
import platform
import threading
from datetime import datetime, timezone

from mcsc_gui.config.settings import DATA_DIR_PATH
from mcsc_gui.telemetry import get_telemetry_client

logger = logging.getLogger(__name__)

MARKER_PATH = os.path.join(DATA_DIR_PATH, "session.lock")

# app_close "reason" detail
REASON_QUIT = "quit"  # the user quit the app
REASON_SESSION_END = "session_end"  # OS shutdown, restart or logoff
REASON_UNCLEAN = "unclean"  # the previous run was killed (sent at the next start)

_close_lock = threading.Lock()
_close_sent = False


def begin(path: str = MARKER_PATH) -> bool:
    """Mark the session as running. Returns True if the previous one didn't end cleanly."""
    unclean = os.path.exists(path)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(datetime.now(timezone.utc).isoformat())
    except OSError:
        logger.exception("Can't write the session marker")
    if unclean:
        logger.warning("The previous session didn't end cleanly")
    return unclean


def end(path: str = MARKER_PATH) -> None:
    """Mark the session as ended cleanly."""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        logger.exception("Can't remove the session marker")


def send_app_close(reason: str, timeout: float = 2) -> bool:
    """Send ``app_close`` (once per run; later calls do nothing). Never raises.

    The event is queued on disk before the request: if the process is killed
    meanwhile, it's sent at the next start. Returns True if this call sent it.
    """
    global _close_sent  # pylint: disable=global-statement
    with _close_lock:
        if _close_sent:
            return False
        _close_sent = True
    try:
        get_telemetry_client().send_event_durable("app_close", {"reason": reason}, timeout=timeout)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Can't send app_close telemetry")
    return True


def send_unclean_close() -> None:
    """``app_close`` for a previous run that was killed. Never raises."""
    try:
        get_telemetry_client().send_event(
            "app_close", {"reason": REASON_UNCLEAN, "delayed": True})
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Can't send the unclean app_close telemetry")


def _reset_for_tests() -> None:
    global _close_sent  # pylint: disable=global-statement
    with _close_lock:
        _close_sent = False


class ShutdownBlocker:
    """Windows only: ask the OS to wait for us before shutting down.

    The block is advisory: Windows lists the app with the reason and the user
    can still force the shutdown. Call it from the thread that owns the window.
    Elsewhere every method does nothing.
    """

    def __init__(self) -> None:
        self.supported = platform.system() == "Windows"
        self._hwnd: int | None = None
        self._reason: str | None = None

    @property
    def active(self) -> bool:
        return self._hwnd is not None

    def block(self, hwnd: int, reason: str) -> None:
        """Block the shutdown on ``hwnd`` (a top-level window, even hidden)."""
        if not self.supported or (hwnd == self._hwnd and reason == self._reason):
            return
        self.release()
        import ctypes  # pylint: disable=import-outside-toplevel

        user32 = ctypes.windll.user32
        user32.ShutdownBlockReasonCreate.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p)
        if user32.ShutdownBlockReasonCreate(ctypes.c_void_p(hwnd), reason):
            self._hwnd, self._reason = hwnd, reason
            logger.info("Shutdown blocked while servers are running")
        else:
            logger.warning(f"ShutdownBlockReasonCreate failed: {ctypes.GetLastError()}")

    def release(self) -> None:
        if not self.supported or self._hwnd is None:
            return
        import ctypes  # pylint: disable=import-outside-toplevel

        user32 = ctypes.windll.user32
        user32.ShutdownBlockReasonDestroy.argtypes = (ctypes.c_void_p,)
        user32.ShutdownBlockReasonDestroy(ctypes.c_void_p(self._hwnd))
        self._hwnd = self._reason = None
        logger.info("Shutdown no longer blocked")
