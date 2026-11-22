"""
Main window: frameless (unless the native title bar is enabled), with
TitleBar + Sidebar + page stack + toasts, and the safe shutdown sequence.

With a tray icon attached (:meth:`MainWindow.attach_tray`) closing the window
only hides it (setting ``close_to_tray``): the app and its servers keep running
until the user quits from the tray.
"""

from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QIcon, QKeySequence, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QSizeGrip,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from mcsc_gui.config import settings as mcssettings
from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.async_bridge import AsyncBridge
from mcsc_gui.core.changelog import load_changelog
from mcsc_gui.core.translations import translate as _
from mcsc_gui.core.user_settings import DEFAULT_CLOSE_TO_TRAY, UserSettings
from mcsc_gui.telemetry import send_event_async
from mcsc_gui.update import get_current_version, launch_updater
from mcsc_gui.ui.dialogs.app_settings import AppSettingsDialog
from mcsc_gui.ui.dialogs.clone_server import CloneServerDialog
from mcsc_gui.ui.dialogs.confirm_quit import ConfirmQuitDialog, ShutdownDialog
from mcsc_gui.ui.dialogs.create_server import CreateServerDialog
from mcsc_gui.ui.dialogs.delete_server import DeleteServerDialog
from mcsc_gui.ui.dialogs.import_server import ImportServerDialog
from mcsc_gui.ui.dialogs.shortcut import ShortcutPromptDialog, mark_prompt_shown, should_prompt
from mcsc_gui.ui.dialogs.update_app import UpdateAppDialog, safe_check_for_updates
from mcsc_gui.ui.dialogs.whats_new import WhatsNewDialog, mark_seen, startup_notes
from mcsc_gui.ui.navigator import (
    BACKUPS,
    CONFIGURATION,
    CONSOLE,
    DASHBOARD,
    EDITOR,
    SERVER,
    SERVER_SETTINGS,
    Navigator,
    Route,
    section_of,
)
from mcsc_gui.ui.pages.config_editor import ConfigEditorPage
from mcsc_gui.ui.pages.dashboard import DashboardPage
from mcsc_gui.ui.pages.server_backups import ServerBackupsPage
from mcsc_gui.ui.pages.server_base import ServerPage
from mcsc_gui.ui.pages.server_configuration import ServerConfigurationPage
from mcsc_gui.ui.pages.server_console import ServerConsolePage
from mcsc_gui.ui.pages.server_overview import ServerOverviewPage
from mcsc_gui.ui.pages.server_settings import ServerSettingsPage
from mcsc_gui.ui.server_events import ServerEvents
from mcsc_gui.ui.tasks import run_blocking, run_task
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.overlay_dialog import OverlayDialog
from mcsc_gui.ui.widgets.sidebar import Sidebar
from mcsc_gui.ui.widgets.title_bar import TitleBar
from mcsc_gui.ui.widgets.toast import ToastManager
from mcsc_gui.utils import get_static_path

logger = logging.getLogger(__name__)

APP_TITLE = "Minecraft Server Creator"
SERVER_PAGES: dict[str, type[ServerPage]] = {
    SERVER: ServerOverviewPage,
    CONSOLE: ServerConsolePage,
    CONFIGURATION: ServerConfigurationPage,
    BACKUPS: ServerBackupsPage,
    SERVER_SETTINGS: ServerSettingsPage,
}
DEFAULT_SIZE = (1300, 800)
MINIMUM_SIZE = (1000, 640)
TELEMETRY_CLOSE_TIMEOUT = 6  # seconds
BACKUP_CLOSE_TIMEOUT = 600  # extra seconds to quit when servers are backed up on stop
STARTUP_PROMPTS_DELAY_MS = 800


async def _shutdown_servers() -> None:
    """Stop every server, then send the app_close event (bounded)."""
    await sm.stop_all_servers()
    try:
        await asyncio.wait_for(send_event_async("app_close"), TELEMETRY_CLOSE_TIMEOUT)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning(f"Can't send app_close telemetry: {e}")


class MainWindow(QMainWindow):
    def __init__(self, events: ServerEvents, bridge: AsyncBridge, *,
                 native_title_bar: bool = False) -> None:
        super().__init__()
        self.events = events
        self.bridge = bridge
        self.native_title_bar = native_title_bar
        self._update_available = False
        self._shutting_down = False
        self._quit_ready = False
        self._update_on_exit = False
        self._prompts_pending = False
        self._prompts_done = False
        self.tray = None  # TrayIcon, see attach_tray
        # Servers started automatically at startup: cancelled when the app quits
        self.auto_start_future = None

        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(QIcon(str(get_static_path("logo.ico"))))
        self.resize(*DEFAULT_SIZE)
        self.setMinimumSize(*MINIMUM_SIZE)
        if not native_title_bar:
            self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                                | Qt.WindowType.WindowMinMaxButtonsHint)

        root = QWidget(self)
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar(root)
        layout.addWidget(self.sidebar)

        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        self.title_bar = TitleBar(root, window_buttons=not native_title_bar)
        content.addWidget(self.title_bar)
        self.stack = QStackedWidget(root)
        self.stack.setObjectName("Pages")
        content.addWidget(self.stack, 1)
        layout.addLayout(content, 1)

        self.size_grip = QSizeGrip(root)
        self.size_grip.setFixedSize(16, 16)
        self.size_grip.setVisible(not native_title_bar)

        self.toasts = ToastManager(root)

        self.dashboard = DashboardPage(events)
        self.navigator = Navigator(self.stack, self.dashboard, self._create_page, self)
        self.navigator.page_changed.connect(self._on_page_changed)

        # ------------------------------------------------------------ wiring
        self.dashboard.open_server.connect(self.navigator.to_server)
        self.dashboard.new_server_requested.connect(self.open_create_dialog)
        self.dashboard.import_server_requested.connect(self.open_import_dialog)
        self.dashboard.edit_server.connect(
            lambda server_id: self.navigator.to_section(server_id, SERVER_SETTINGS))
        self.dashboard.clone_server.connect(self._clone_from_dashboard)
        self.dashboard.delete_server.connect(self._delete_from_dashboard)
        self.sidebar.dashboard_clicked.connect(self.navigator.to_dashboard)
        self.sidebar.section_clicked.connect(self.navigator.to_section)
        for signal in (events.state_changed, events.server_updated, events.busy_changed):
            signal.connect(lambda server_id, *_args: self.sidebar.refresh_server(server_id))
        self.sidebar.new_server_clicked.connect(self.open_create_dialog)
        self.sidebar.updates_clicked.connect(self.on_updates_clicked)
        self.sidebar.settings_clicked.connect(self.open_settings_dialog)
        self.title_bar.back_requested.connect(self.navigator.back)
        self.title_bar.minimize_requested.connect(self.showMinimized)
        self.title_bar.maximize_requested.connect(self.toggle_maximized)
        self.title_bar.close_requested.connect(self.close_by_user)
        events.server_removed.connect(self._on_server_removed)

        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.open_create_dialog)
        QShortcut(QKeySequence("Alt+Left"), self, activated=self.navigator.back)
        QShortcut(QKeySequence(QKeySequence.StandardKey.Back), self,
                  activated=self.navigator.back)

        self._on_page_changed(DASHBOARD)

    # ------------------------------------------------------------- pages

    def _create_page(self, route: Route) -> QWidget | None:
        server = sm.find_server(route.args[0]) if route.args else None
        if server is None:
            self.toasts.error(_("Invalid server"))
            return None
        page_class = SERVER_PAGES.get(route.kind)
        if page_class is not None:
            page = page_class(server, self.events)
            page.edit_file_requested.connect(self.navigator.to_editor)
            page.section_requested.connect(self.navigator.to_section)
            page.delete_requested.connect(lambda _id, s=server: self.open_delete_dialog(s))
            page.clone_requested.connect(
                lambda _id, s=server: self.open_clone_dialog(s, open_copy=True))
            page.title_changed.connect(self._set_title)
            return page
        if route.kind == EDITOR:
            filename = route.args[1]
            if filename not in server.CONFIG_FILES:
                self.toasts.error(_("Invalid server"))
                return None
            page = ConfigEditorPage(server, filename)
            page.title_changed.connect(self._set_title)
            return page
        return None

    def _set_title(self, title: str) -> None:
        self.title_bar.set_title(title)
        dashboard = self.navigator.current_route.kind == DASHBOARD
        self.setWindowTitle(APP_TITLE if dashboard else f"{title} — {APP_TITLE}")

    def _on_page_changed(self, kind: str) -> None:
        page = self.navigator.current_page
        self._set_title(page.page_title() if hasattr(page, "page_title") else _("Dashboard"))
        self.title_bar.set_back_visible(self.navigator.can_go_back)
        route = self.navigator.current_route
        section = section_of(route)
        server = sm.find_server(route.args[0]) if section and route.args else None
        if server is not None:
            self.sidebar.show_server(server, section)
        else:
            self.sidebar.show_app_menu()
            self.sidebar.set_active("dashboard" if kind == DASHBOARD else None)

    def _on_server_removed(self, server_id: str) -> None:
        route = self.navigator.current_route
        if section_of(route) and route.args and route.args[0] == server_id:
            self.navigator.to_dashboard()

    # ----------------------------------------------------------- dialogs

    def open_dialog(self, dialog: OverlayDialog) -> OverlayDialog:
        dialog.open()
        return dialog

    def open_create_dialog(self) -> None:
        if self._shutting_down:
            return
        dialog = CreateServerDialog(self)
        dialog.created.connect(self.navigator.to_dashboard)
        self.open_dialog(dialog)

    def open_import_dialog(self) -> None:
        if self._shutting_down:
            return
        dialog = ImportServerDialog(self)
        dialog.imported.connect(self.navigator.to_server)
        self.open_dialog(dialog)

    def open_delete_dialog(self, server) -> None:
        dialog = DeleteServerDialog(self, server)
        dialog.deleted.connect(lambda _id: self.navigator.to_dashboard())
        self.open_dialog(dialog)

    def open_clone_dialog(self, server, *, open_copy: bool = False) -> None:
        """Clone ``server``; with ``open_copy`` the new server's page opens at the end."""
        if self._shutting_down:
            return
        dialog = CloneServerDialog(self, server)
        if open_copy:
            dialog.cloned.connect(self.navigator.to_server)

        def removed(server_id: str) -> None:
            if server_id == server.id and not dialog.busy:
                dialog.reject()

        self.events.server_removed.connect(removed)
        dialog.closed.connect(lambda: self.events.server_removed.disconnect(removed))
        self.open_dialog(dialog)

    def _clone_from_dashboard(self, server_id: str) -> None:
        server = sm.find_server(server_id)
        if server is not None:
            self.open_clone_dialog(server)

    def _delete_from_dashboard(self, server_id: str) -> None:
        server = sm.find_server(server_id)
        if server is not None:
            self.open_delete_dialog(server)

    def open_settings_dialog(self) -> None:
        dialog = AppSettingsDialog(self)
        dialog.changelog_requested.connect(self.open_changelog_dialog)
        self.open_dialog(dialog)

    def open_changelog_dialog(self) -> None:
        """The full release history (from the App Settings)."""
        if self._shutting_down:
            return
        self.open_dialog(WhatsNewDialog(self, load_changelog(), title=_("Changelog")))
        self._send_whats_new_event("settings")

    def schedule_startup_prompts(self) -> None:
        """Show the startup prompts once the window is visible (later if it starts hidden)."""
        self._prompts_pending = True
        if self.isVisible():
            self._show_pending_prompts()

    def _show_pending_prompts(self) -> None:
        if not self._prompts_pending or self._prompts_done:
            return
        self._prompts_pending = False
        self._prompts_done = True
        QTimer.singleShot(STARTUP_PROMPTS_DELAY_MS, self.run_startup_prompts)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._show_pending_prompts()

    def run_startup_prompts(self) -> None:
        """One popup at startup: the notes after an update, else the shortcut prompt."""
        if not self.maybe_show_whats_new():
            self.maybe_prompt_shortcut()

    def maybe_show_whats_new(self) -> bool:
        """After an update: show what's new since the last version used. True if shown."""
        if self._shutting_down:
            return False
        current = get_current_version()
        try:
            settings = UserSettings()
            notes = startup_notes(settings, current, load_changelog(),
                                  has_servers=bool(sm.get_servers()))
            # Saved before showing it: whatever happens next, it's never shown twice
            mark_seen(settings, current)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Can't check what's new")
            return False
        if not notes:
            return False
        self.open_dialog(WhatsNewDialog(self, notes, close_text=_("Got it")))
        self._send_whats_new_event("startup")
        return True

    def _send_whats_new_event(self, source: str) -> None:
        details = {"source": source, "version": get_current_version()}
        run_task(send_event_async("whats_new_shown", details=details), show_errors=False)

    def maybe_prompt_shortcut(self) -> None:
        """First launch only: offer to add a desktop shortcut."""
        if self._shutting_down:
            return
        try:
            settings = UserSettings()
            if not should_prompt(settings):
                return
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Can't check the desktop shortcut")
            return
        # Saved before showing it: whatever the answer (or a crash), it's never shown again
        mark_prompt_shown(settings)
        self.open_dialog(ShortcutPromptDialog(self, settings))

    # ----------------------------------------------------------- updates

    def start_update_check(self) -> None:
        """Check PyPI in the background at startup (never blocks, never fails)."""
        run_blocking(safe_check_for_updates, on_success=self._set_update_available,
                     show_errors=False)

    def _set_update_available(self, available: bool, notify: bool = True) -> None:
        self._update_available = bool(available)
        self.sidebar.set_update_available(self._update_available)
        if available and notify:
            if self.tray is not None and not self.isVisible():
                self.tray.notify(_("Update available"))
            else:
                self.toasts.info(_("Update available"), timeout_ms=10_000)

    def on_updates_clicked(self) -> None:
        if self._update_available:
            self.open_update_dialog()
            return
        handle = self.toasts.progress(_("Checking for updates..."))

        def checked(available: bool) -> None:
            self._set_update_available(available, notify=False)
            if available:
                handle.succeed(_("Update available"))
                self.open_update_dialog()
            else:
                handle.succeed(_("No updates available"))

        run_blocking(safe_check_for_updates, disable=[self.sidebar.updates_button],
                     on_success=checked, show_errors=False)

    def open_update_dialog(self) -> None:
        dialog = UpdateAppDialog(self)
        dialog.update_requested.connect(lambda: self.request_quit(confirm=True, update=True))
        self.open_dialog(dialog)

    # ------------------------------------------------------------ window

    def toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def bring_to_front(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    # -------------------------------------------------------------- tray

    def attach_tray(self, tray) -> None:
        """Use ``tray`` (a :class:`~mcsc_gui.ui.tray.TrayIcon`): closing hides the window."""
        self.tray = tray
        tray.open_requested.connect(self.bring_to_front)
        tray.stop_all_requested.connect(self.stop_all_servers)
        tray.quit_requested.connect(self.quit_from_tray)

    def close_to_tray_enabled(self) -> bool:
        if self.tray is None:
            return False
        try:
            settings = UserSettings().user_settings
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Can't read the user settings")
            return DEFAULT_CLOSE_TO_TRAY
        return bool(settings.get("close_to_tray", DEFAULT_CLOSE_TO_TRAY))

    def close_by_user(self) -> None:
        """The user closed the window: hide it in the tray or quit."""
        if self._shutting_down:
            return
        if self.close_to_tray_enabled():
            self.hide_to_tray()
        else:
            self.request_quit(confirm=True)

    def hide_to_tray(self) -> None:
        self.hide()
        self._maybe_show_tray_hint()

    def _maybe_show_tray_hint(self) -> None:
        """The first time only: tell the user the app is still running."""
        try:
            settings = UserSettings()
            if settings.user_settings.get("tray_hint_shown"):
                return
            settings.update_settings(tray_hint_shown=True)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Can't save the tray hint flag")
            return
        if self.tray is not None:
            self.tray.notify(_("Minecraft Server Creator is still running in the tray. "
                               "Right-click the icon to quit."))

    def stop_all_servers(self) -> None:
        if self._shutting_down or not sm.any_server_active():
            return
        run_task(sm.stop_all_servers(), progress=_("Stopping all servers..."),
                 success=_("All servers stopped"))

    def quit_from_tray(self) -> None:
        """Quit with the usual confirmation, shown in the window."""
        if self._shutting_down:
            self.bring_to_front()
            return
        self.bring_to_front()
        self.request_quit(confirm=True)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt API
        if event.type() == QEvent.Type.WindowStateChange:
            maximized = self.isMaximized()
            self.title_bar.set_maximized(maximized)
            self.size_grip.setVisible(not maximized and not self.native_title_bar)
        super().changeEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        root = self.centralWidget()
        self.size_grip.move(root.width() - self.size_grip.width(),
                            root.height() - self.size_grip.height())
        self.size_grip.raise_()

    # ---------------------------------------------------------- shutdown

    @property
    def shutting_down(self) -> bool:
        return self._shutting_down

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if self._quit_ready:
            event.accept()
            return
        event.ignore()
        if event.spontaneous():  # the system title bar's X, Alt+F4
            self.close_by_user()
        else:  # programmatic (e.g. the app is asked to quit)
            if not self.isVisible():
                self.bring_to_front()  # the confirmation must be visible
            self.request_quit(confirm=True)

    def request_quit(self, *, confirm: bool = True, update: bool = False) -> None:
        """Quit safely: confirm, stop every server, send telemetry, then exit.

        With ``update`` the standalone updater is started once the app is
        about to exit (pip can't replace the files of a running app).
        """
        if self._shutting_down:
            return
        page = self.navigator.current_page
        if confirm and hasattr(page, "can_leave") and not page.can_leave():
            page.confirm_leave(lambda: self.request_quit(confirm=confirm, update=update))
            return
        operations = sm.any_operation_running()
        if confirm and (sm.any_server_active() or operations):
            dialog = ConfirmQuitDialog(self, operations=operations)
            dialog.accepted.connect(lambda: self._shutdown(update=update))
            self.open_dialog(dialog)
            return
        self._shutdown(update=update)

    def _shutdown(self, *, update: bool = False) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self._update_on_exit = update
        logger.info("Shutting down the app...")
        if self.auto_start_future is not None:
            self.auto_start_future.cancel()  # don't start more servers while quitting
        # "On stop" automatic backups run after the servers stop: wait for them too
        backing_up = sm.pending_backups() > 0 or any(
            sm.effective_backup_policy(s) == "on_stop" for s in sm.manager.active_servers)
        if sm.any_server_active() or backing_up:
            self.open_dialog(ShutdownDialog(self, backing_up=backing_up))
        # Never wait forever: servers are killed after SERVER_STOP_TIMEOUT anyway
        timeout = mcssettings.SERVER_STOP_TIMEOUT + TELEMETRY_CLOSE_TIMEOUT + 10
        if backing_up:
            timeout += BACKUP_CLOSE_TIMEOUT
        QTimer.singleShot(timeout * 1000, self._finish_quit)
        future = run_task(_shutdown_servers(), on_success=lambda _r: self._finish_quit(),
                          on_error=lambda _e: self._finish_quit(), show_errors=False)
        if future is None:
            self._finish_quit()

    def _finish_quit(self) -> None:
        if self._quit_ready or not isValid(self):
            return
        self._quit_ready = True
        if self.tray is not None:
            self.tray.hide()
        if self._update_on_exit and not launch_updater():
            logger.error("The updater didn't start: the app closes without updating")
        self.events.close()
        self.close()
        QApplication.quit()
