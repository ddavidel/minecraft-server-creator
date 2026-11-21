"""
Bootstrap of the Qt (PySide6) desktop app.

Order: logging -> QApplication -> single instance -> theme -> servers registry
(+ legacy migration) -> asyncio bridge -> events -> window + tray icon ->
background work (autostart entry, versions preload, auto start servers,
telemetry, update check) -> event loop -> safe shutdown.

``--background`` (used by the login autostart entry) starts the app in the
tray without showing the window.
"""

from __future__ import annotations

import atexit
import logging
import signal
import sys
import traceback
from types import TracebackType

from mcsc_gui._pymcsc_check import ensure_pymcsc

# Must run before anything imports the pymcsc library (``mcsc``)
ensure_pymcsc()

# pylint: disable=wrong-import-position
from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtGui import QGuiApplication, QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from mcsc_gui.config import settings as mcssettings  # noqa: E402
from mcsc_gui.core import server_manager as sm  # noqa: E402
from mcsc_gui.core import autostart  # noqa: E402
from mcsc_gui.core import stats_history  # noqa: E402
from mcsc_gui.core.async_bridge import get_bridge  # noqa: E402
from mcsc_gui.core.logger import setup_logging  # noqa: E402
from mcsc_gui.core.migration import migrate_legacy  # noqa: E402
from mcsc_gui.core.notifier import set_notifier  # noqa: E402
from mcsc_gui.core.os_utils import hide_child_consoles  # noqa: E402
from mcsc_gui.core.shortcuts import set_windows_app_id  # noqa: E402
from mcsc_gui.core.shutdown import emergency_stop  # noqa: E402
from mcsc_gui.core.translations import translate as _  # noqa: E402
from mcsc_gui.core.user_settings import DEFAULT_NATIVE_TITLE_BAR, UserSettings  # noqa: E402
from mcsc_gui.telemetry import get_telemetry_client  # noqa: E402
from mcsc_gui.ui import tasks  # noqa: E402
from mcsc_gui.ui.invoke import install_invoker, invoke_in_ui  # noqa: E402
from mcsc_gui.ui.main_window import APP_TITLE, MainWindow  # noqa: E402
from mcsc_gui.ui.server_events import ServerEvents  # noqa: E402
from mcsc_gui.ui.single_instance import SingleInstance  # noqa: E402
from mcsc_gui.ui.tray import TrayIcon, TrayNotifier, window_visible  # noqa: E402
from mcsc_gui.ui.theme.fonts import load_fonts  # noqa: E402
from mcsc_gui.ui.theme.qss import build_stylesheet  # noqa: E402
from mcsc_gui.update import get_current_version  # noqa: E402
from mcsc_gui.utils import get_static_path  # noqa: E402

logger = logging.getLogger("mcsc_gui.qt")


def _send_app_start() -> None:
    get_telemetry_client().send_event(
        event_name="app_start",
        details={"version": get_current_version(), "ui": "qt"},
    )


def _install_safety_net(bridge, window: MainWindow) -> QTimer:
    """atexit, excepthook and Ctrl+C handlers (FR-006). Returns the SIGINT wake-up timer."""
    atexit.register(emergency_stop, bridge)

    previous_hook = sys.excepthook

    def excepthook(exc_type: type[BaseException], exc: BaseException,
                   tb: TracebackType | None) -> None:
        logger.critical("Unhandled exception:\n%s",
                        "".join(traceback.format_exception(exc_type, exc, tb)))
        if issubclass(exc_type, KeyboardInterrupt):
            invoke_in_ui(lambda: window.request_quit(confirm=False))
            return
        # Exceptions in Qt slots don't stop the app: report them and keep going.
        invoke_in_ui(lambda: window.toasts.error(_("Unexpected error: {error}", error=exc)))
        if previous_hook not in (None, sys.__excepthook__):
            previous_hook(exc_type, exc, tb)

    sys.excepthook = excepthook

    def on_sigint(_signum, _frame) -> None:
        logger.info("SIGINT received: closing")
        invoke_in_ui(lambda: window.request_quit(confirm=False))

    signal.signal(signal.SIGINT, on_sigint)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, on_sigint)
    # Python only runs signal handlers when it gets control back from Qt's C++ loop
    wake = QTimer()
    wake.start(250)
    wake.timeout.connect(lambda: None)
    return wake


def _sync_autostart() -> None:
    """Align the login autostart entry with the setting (never fails)."""
    try:
        autostart.sync(UserSettings())
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Can't update the autostart entry")


async def _auto_start_servers() -> None:
    try:
        await sm.auto_start_servers()
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Auto start of the servers failed")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    debug = "--debug" in argv or mcssettings.DEBUG
    background = autostart.BACKGROUND_ARG in argv
    setup_logging(debug=debug)
    logger.info("Starting Minecraft Server Creator (Qt)%s", " in the background" if background else "")
    set_windows_app_id()  # before any window: taskbar shows MCSC, not Python
    hide_child_consoles()  # pythonw: java servers must not open a terminal

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName(APP_TITLE)
    app.setOrganizationName("mcsc")
    app.setApplicationVersion(get_current_version())
    app.setDesktopFileName("mcsc")  # Linux: match the mcsc.desktop shortcut
    app.setWindowIcon(QIcon(str(get_static_path("logo.ico"))))

    instance = SingleInstance()
    if not instance.acquire():
        return 0

    install_invoker()
    app.setStyle("Fusion")
    load_fonts()
    app.setStyleSheet(build_stylesheet())

    sm.load_servers()
    try:
        migrate_legacy()
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Legacy migration failed")
    sm.cleanup_temporary_files()  # interrupted backups, restores and imports

    bridge = get_bridge()
    bridge.start()
    events = ServerEvents()
    events.attach_all(sm.get_servers())

    native = bool(UserSettings().user_settings.get("native_title_bar", DEFAULT_NATIVE_TITLE_BAR))
    window = MainWindow(events, bridge, native_title_bar=native)
    tasks.configure(bridge, window.toasts)
    tray = TrayIcon(events) if TrayIcon.available() else None
    if tray is not None:
        window.attach_tray(tray)
        tray.show()
        set_notifier(TrayNotifier(window.toasts, tray, window_visible(window)))
    else:
        set_notifier(tasks.ToastNotifier(window.toasts))
    # Hidden in the tray, the window isn't the "last window": don't quit when it hides
    app.setQuitOnLastWindowClosed(tray is None)
    instance.activated.connect(window.bring_to_front)
    wake = _install_safety_net(bridge, window)

    if not background:
        window.show()
    elif tray is None:
        window.showMinimized()  # no tray to start in
    window.schedule_startup_prompts()  # What's New or shortcut prompt, once visible

    # Background work: never blocks the window from showing
    bridge.call(_sync_autostart)
    bridge.call(sm.preload_versions)
    bridge.call(stats_history.prune_old)
    window.auto_start_future = bridge.submit(_auto_start_servers())
    bridge.call(_send_app_start)
    window.start_update_check()

    code = app.exec()

    wake.stop()
    emergency_stop(bridge)  # no-op after a normal close
    bridge.shutdown()
    set_notifier(None)
    if tray is not None:
        tray.hide()
    instance.release()
    logger.info("Bye")
    return code


if __name__ == "__main__":
    sys.exit(main())
