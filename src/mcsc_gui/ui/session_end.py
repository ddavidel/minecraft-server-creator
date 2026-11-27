"""
OS shutdown, restart or logoff while the app runs (often hidden in the tray).

On ``WM_ENDSESSION`` Qt only emits ``aboutToQuit`` and quits, and Windows ends
the process as soon as the message returns: the window's quit sequence
(:meth:`MainWindow.request_quit`) never runs. :class:`SessionEndHandler` does
its work synchronously in ``aboutToQuit`` instead: stop the servers, close the
session, send ``app_close``.

While a server runs (or a backup, restore... is in progress) the window keeps a
Windows shutdown block reason, so the OS waits for the servers to save instead
of killing Java right away.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from mcsc_gui.config import settings as mcssettings
from mcsc_gui.core import server_manager as sm
from mcsc_gui.core import session
from mcsc_gui.core.async_bridge import AsyncBridge
from mcsc_gui.core.shutdown import emergency_stop
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.main_window import BACKUP_CLOSE_TIMEOUT, MainWindow
from mcsc_gui.ui.server_events import ServerEvents

logger = logging.getLogger(__name__)


def _busy() -> bool:
    """Something that must not be cut short by the OS shutting down."""
    return sm.any_server_active() or sm.pending_backups() > 0 or sm.any_operation_running()


class SessionEndHandler(QObject):
    def __init__(self, app: QApplication, window: MainWindow, events: ServerEvents,
                 bridge: AsyncBridge, blocker: session.ShutdownBlocker | None = None) -> None:
        super().__init__(window)
        self.window = window
        self.bridge = bridge
        self.blocker = blocker or session.ShutdownBlocker()
        self.handled = False
        app.aboutToQuit.connect(self.on_about_to_quit)
        events.state_changed.connect(self.refresh_block)
        events.busy_changed.connect(self.refresh_block)
        # New native window (title bar changed) or new language: block again
        window.ui_rebuilt.connect(self.refresh_block)

    def refresh_block(self, *_args) -> None:
        """Block the OS shutdown only while there's something to stop safely."""
        if not self.blocker.supported or self.handled or not isValid(self.window):
            return
        if _busy():
            # winId() creates the native window if needed: it works while hidden
            self.blocker.block(int(self.window.winId()),
                               _("Stopping all servers, please wait…"))
        else:
            self.blocker.release()

    def on_about_to_quit(self) -> None:
        if self.handled:
            return
        self.handled = True
        if self.window.quit_ready:
            # Normal quit: servers already stopped and app_close already sent
            self.blocker.release()
            return
        logger.warning("The session is ending: stopping the servers before the OS closes the app")
        timeout = mcssettings.SERVER_STOP_TIMEOUT + 5
        if sm.pending_backups() > 0:
            timeout += BACKUP_CLOSE_TIMEOUT
        try:
            emergency_stop(self.bridge, timeout)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Stopping the servers at session end failed")
        session.end()
        session.send_app_close(session.REASON_SESSION_END)
        self.blocker.release()
        logger.info("Session end handled")
