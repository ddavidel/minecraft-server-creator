"""
System tray icon: the app keeps running (with its servers) when the window is closed.

:class:`TrayIcon` shows the icon and its menu (open the window, running servers,
stop them all, quit) and native notifications. :class:`TrayNotifier` is the
core notifier while the tray exists: toasts when the window is visible, tray
notifications for errors and warnings while it's hidden.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSystemTrayIcon, QWidget
from shiboken6 import isValid

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.invoke import invoke_in_ui
from mcsc_gui.ui.server_events import ServerEvents
from mcsc_gui.ui.tasks import ToastNotifier
from mcsc_gui.ui.widgets.context_menu import ContextMenu
from mcsc_gui.ui.widgets.toast import ToastManager
from mcsc_gui.utils import get_static_path

APP_NAME = "Minecraft Server Creator"
MESSAGE_TIMEOUT_MS = 8000

_ICONS = {
    "info": QSystemTrayIcon.MessageIcon.Information,
    "success": QSystemTrayIcon.MessageIcon.Information,
    "warning": QSystemTrayIcon.MessageIcon.Warning,
    "error": QSystemTrayIcon.MessageIcon.Critical,
}


class TrayIcon(QObject):
    """The app's tray icon. Create it only if :meth:`available`."""

    open_requested = Signal()
    stop_all_requested = Signal()
    quit_requested = Signal()

    def __init__(self, events: ServerEvents | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.icon = QSystemTrayIcon(QIcon(str(get_static_path("logo.ico"))), self)
        self.menu = ContextMenu()
        self.menu.aboutToShow.connect(self.rebuild_menu)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._on_activated)
        self.icon.messageClicked.connect(self.open_requested)
        if events is not None:
            for signal in (events.state_changed, events.server_added, events.server_removed,
                           events.server_updated):
                signal.connect(lambda *_args: self.refresh())
        self.rebuild_menu()
        self.refresh()

    @staticmethod
    def available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def show(self) -> None:
        self.icon.show()

    def hide(self) -> None:
        self.icon.hide()

    def refresh(self) -> None:
        """Update the tooltip with the number of running servers."""
        count = len(_active_servers())
        if count == 0:
            tooltip = APP_NAME
        elif count == 1:
            tooltip = f"{APP_NAME}\n" + _("1 server running")
        else:
            tooltip = f"{APP_NAME}\n" + _("{count} servers running", count=count)
        self.icon.setToolTip(tooltip)

    def rebuild_menu(self) -> None:
        """Open / running servers / Stop all / Quit (rebuilt each time it opens)."""
        menu = self.menu
        menu.clear()
        open_action = menu.add_action(_("Open {app}", app=APP_NAME), "open_in_new")
        open_action.triggered.connect(self.open_requested)
        menu.addSeparator()
        active = _active_servers()
        if active:
            title = menu.addAction(_("Running servers"))
            title.setEnabled(False)
            for server in active:
                item = menu.addAction(f"{server.name} · {sm.status_label(server.state)}")
                item.triggered.connect(self.open_requested)
        else:
            empty = menu.addAction(_("No servers running"))
            empty.setEnabled(False)
        stop_all = menu.add_action(_("Stop all servers"), "stop")
        stop_all.setEnabled(bool(active))
        stop_all.triggered.connect(self.stop_all_requested)
        menu.addSeparator()
        quit_action = menu.add_danger_action(_("Quit"), "close")
        quit_action.triggered.connect(self.quit_requested)

    def notify(self, message: str, level: str = "info", title: str = APP_NAME) -> None:
        """A native notification next to the tray icon."""
        if self.icon.isVisible():
            self.icon.showMessage(title, message, _ICONS.get(level, _ICONS["info"]),
                                  MESSAGE_TIMEOUT_MS)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.open_requested.emit()


def _active_servers():
    return [s for s in sm.get_servers() if s.is_active]


class TrayNotifier(ToastNotifier):
    """Toasts while the window is visible; tray notifications (errors, warnings) otherwise.

    Callable from any thread: the choice is made in the UI thread.
    """

    def __init__(self, manager: ToastManager, tray: TrayIcon,
                 window_visible: Callable[[], bool]) -> None:
        super().__init__(manager)
        self._tray = tray
        self._window_visible = window_visible

    def _show(self, level: str, message: str) -> None:
        def show() -> None:
            hidden = not self._window_visible()
            if hidden and level in ("error", "warning") and isValid(self._tray):
                self._tray.notify(message, level)
            elif isValid(self._manager):
                getattr(self._manager, level)(message)

        invoke_in_ui(show)


def window_visible(window: QWidget) -> Callable[[], bool]:
    """``window_visible`` callback for :class:`TrayNotifier`."""
    return lambda: isValid(window) and window.isVisible() and not window.isMinimized()
