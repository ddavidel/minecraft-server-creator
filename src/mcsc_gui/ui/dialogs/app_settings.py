"""App settings dialog (US6): version, language, title bar, startup and tray, automatic backups."""

from __future__ import annotations

import platform

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QSystemTrayIcon,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mcsc_gui.config import settings as mcssettings
from mcsc_gui.core import server_manager as sm
from mcsc_gui.core import autostart, shortcuts
from mcsc_gui.core.translations import current_language, languages_map
from mcsc_gui.core.translations import translate as _
from mcsc_gui.core.user_settings import (
    AUTO_BACKUP_POLICIES,
    DEFAULT_CLOSE_TO_TRAY,
    DEFAULT_AUTO_BACKUP,
    DEFAULT_BACKUP_RETENTION,
    DEFAULT_NATIVE_TITLE_BAR,
    UserSettings,
)
from mcsc_gui.telemetry import send_event_async
from mcsc_gui.ui.dialogs.fields import Field
from mcsc_gui.ui.dialogs.shortcut import create_shortcuts, menu_name
from mcsc_gui.ui.tasks import run_blocking, run_task
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.common import button, label
from mcsc_gui.ui.widgets.overlay_dialog import OverlayDialog
from mcsc_gui.update import get_current_version
from mcsc_gui.utils import get_static_path


class AppSettingsDialog(OverlayDialog):
    # The user asked for the changelog: the dialog closes, the window opens it
    changelog_requested = Signal()
    # The settings were saved (their values): the window applies them, no restart
    saved = Signal(dict)

    def __init__(self, parent: QWidget, user_settings: UserSettings | None = None) -> None:
        super().__init__(parent, _("App Settings"), width=480)
        self._settings = user_settings or UserSettings()
        current = self._settings.user_settings

        about = QHBoxLayout()
        about.setSpacing(TOKENS.spacing.md)
        logo = QLabel()
        pixmap = QPixmap(str(get_static_path("logo.png")))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaledToHeight(56, Qt.TransformationMode.SmoothTransformation))
        about.addWidget(logo)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        # Wrap so the name is never clipped next to the (wide) logo
        texts.addWidget(label("Minecraft Server Creator", "title", wrap=True))
        texts.addWidget(label(_("Version: {version}", version=get_current_version()), "muted"))
        about.addLayout(texts, 1)
        self.body.addLayout(about)

        self.language = QComboBox()
        for code in mcssettings.AVAILABLE_LANGAGUES:
            self.language.addItem(languages_map.get(code, code), code)
        index = self.language.findData(current.get("language", current_language()))
        self.language.setCurrentIndex(max(0, index))
        self.body.addWidget(Field(_("Language"), self.language))

        self.native_title_bar = QCheckBox(_("Use the system title bar"))
        self.native_title_bar.setChecked(bool(current.get("native_title_bar", DEFAULT_NATIVE_TITLE_BAR)))
        self.body.addWidget(self.native_title_bar)

        # Startup: applied as soon as the settings are saved (no restart)
        self.start_with_os = None
        self._autostart_enabled = False
        if autostart.is_supported():
            # The real OS entry, compared on save to add or remove it
            self._autostart_enabled = autostart.is_enabled()
            # On by default (setting not saved yet); off if turned off from Task Manager
            wanted = bool(current.get(autostart.SETTING, autostart.DEFAULT_ENABLED))
            self.start_with_os = QCheckBox(start_with_os_text())
            self.start_with_os.setChecked(
                self._autostart_enabled or (wanted and not autostart.is_disabled_by_user()))
            self.start_with_os.setToolTip(
                _("Starts in the system tray, without opening the window."))
            self.body.addWidget(self.start_with_os)
            if autostart.is_disabled_by_user():
                self.body.addWidget(label(
                    _("Turned off from Task Manager: check the box to turn it back on."),
                    "muted", wrap=True))
        self.close_to_tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.close_to_tray = QCheckBox(
                _("Keep running in the system tray when the window is closed"))
            self.close_to_tray.setChecked(
                bool(current.get("close_to_tray", DEFAULT_CLOSE_TO_TRAY)))
            self.close_to_tray.setToolTip(
                _("The servers keep running. Quit from the tray icon's menu."))
            self.body.addWidget(self.close_to_tray)

        backups = QHBoxLayout()
        backups.setSpacing(TOKENS.spacing.md)
        self.auto_backup = QComboBox()
        for policy in AUTO_BACKUP_POLICIES:
            self.auto_backup.addItem(_(sm.BACKUP_POLICY_LABELS[policy]), policy)
        index = self.auto_backup.findData(current.get("auto_backup", DEFAULT_AUTO_BACKUP))
        self.auto_backup.setCurrentIndex(max(0, index))
        backups.addWidget(Field(_("Automatic backups"), self.auto_backup), 1)
        self.backup_retention = QSpinBox()
        self.backup_retention.setRange(0, 100)
        # The QSS padding doesn't reach the spin box's inner text field: align it by hand
        self.backup_retention.lineEdit().setTextMargins(TOKENS.spacing.md, 0, 0, 0)
        self.backup_retention.setSpecialValueText(_("Unlimited"))
        try:
            retention = int(current.get("backup_retention", DEFAULT_BACKUP_RETENTION))
        except (TypeError, ValueError):
            retention = DEFAULT_BACKUP_RETENTION
        self.backup_retention.setValue(retention)
        self.backup_retention.setToolTip(
            _("Automatic backups kept per server. Manual backups are never deleted."))
        backups.addWidget(Field(_("Automatic backups to keep"), self.backup_retention), 1)
        self.body.addLayout(backups)

        self.shortcut_button = None
        if shortcuts.is_supported():
            shortcut_row = QHBoxLayout()
            shortcut_row.setSpacing(TOKENS.spacing.md)
            shortcut_row.addWidget(label(
                _("Open the app from the desktop and the {menu}.", menu=menu_name()),
                "muted", wrap=True), 1)
            self.shortcut_button = button(_("Create desktop shortcut"), "shortcut")
            self.shortcut_button.clicked.connect(self.create_shortcut)
            shortcut_row.addWidget(self.shortcut_button)
            self.body.addLayout(shortcut_row)

        # Left of the footer, away from Close/Save
        self.changelog_button = button(_("Changelog"), "history", variant="ghost")
        self.changelog_button.clicked.connect(self.show_changelog)
        self.buttons.insertWidget(0, self.changelog_button)

        self.cancel_button = self.add_button(button(_("Close"), "close"))
        self.save_button = self.add_button(button(_("Save"), "save", variant="primary"))
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.submit)

    def show_changelog(self) -> None:
        """Close the settings (unsaved changes are discarded) and ask for the changelog."""
        if self.busy:
            return
        self.reject()
        self.changelog_requested.emit()

    def create_shortcut(self) -> None:
        create_shortcuts(settings=self._settings, disable=[self.shortcut_button])

    def values(self) -> dict:
        values = {
            "language": self.language.currentData(),
            "native_title_bar": self.native_title_bar.isChecked(),
            "auto_backup": self.auto_backup.currentData(),
            "backup_retention": self.backup_retention.value(),
        }
        if self.start_with_os is not None:
            values["start_with_os"] = self.start_with_os.isChecked()
        if self.close_to_tray is not None:
            values["close_to_tray"] = self.close_to_tray.isChecked()
        return values

    def _save(self, **values) -> None:
        """Save the settings, then add or remove the login autostart entry if it changed."""
        self._settings.update_settings(**values)
        enabled = values.get("start_with_os")
        if enabled is not None and enabled != self._autostart_enabled:
            autostart.set_enabled(enabled)
            self._autostart_enabled = enabled

    def submit(self) -> None:
        values = self.values()

        def saved(_result) -> None:
            details = dict(self._settings.user_settings)
            run_task(send_event_async("settings_change", details=details), show_errors=False)
            self.accept()
            # After closing: the window may rebuild its UI (e.g. in the new language)
            self.saved.emit(values)

        run_blocking(self._save, progress=_("Saving"), success=_("Settings saved"),
                     disable=[self.save_button, self.cancel_button, self.changelog_button],
                     on_success=saved, **values)


def start_with_os_text() -> str:
    if platform.system() == "Windows":
        return _("Start MCSC when Windows starts")
    return _("Start MCSC when you log in")
