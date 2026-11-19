"""App settings dialog (US6): version, language, native title bar."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from mcsc_gui.config import settings as mcssettings
from mcsc_gui.core import shortcuts
from mcsc_gui.core.translations import languages_map
from mcsc_gui.core.translations import translate as _
from mcsc_gui.core.user_settings import UserSettings
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
        texts.addWidget(label("Minecraft Server Creator", "title"))
        texts.addWidget(label(_("Version: {version}", version=get_current_version()), "muted"))
        about.addLayout(texts, 1)
        self.body.addLayout(about)

        self.language = QComboBox()
        for code in mcssettings.AVAILABLE_LANGAGUES:
            self.language.addItem(languages_map.get(code, code), code)
        index = self.language.findData(current.get("language", mcssettings.DEFAULT_LANGUAGE))
        self.language.setCurrentIndex(max(0, index))
        self.body.addWidget(Field(_("Language"), self.language))

        self.native_title_bar = QCheckBox(_("Use the system title bar"))
        self.native_title_bar.setChecked(bool(current.get("native_title_bar", False)))
        self.body.addWidget(self.native_title_bar)

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

        self.restart_label = label(
            _("Some settings require a restart to take effect. "
              "Please restart the app after changing them."), "warning", wrap=True)
        self.body.addWidget(self.restart_label)

        self.cancel_button = self.add_button(button(_("Close"), "close"))
        self.save_button = self.add_button(button(_("Save"), "save", variant="primary"))
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.submit)

    def create_shortcut(self) -> None:
        create_shortcuts(settings=self._settings, disable=[self.shortcut_button])

    def values(self) -> dict:
        return {
            "language": self.language.currentData(),
            "native_title_bar": self.native_title_bar.isChecked(),
        }

    def submit(self) -> None:
        values = self.values()

        def saved(_result) -> None:
            details = dict(self._settings.user_settings)
            run_task(send_event_async("settings_change", details=details), show_errors=False)
            self.accept()

        run_blocking(self._settings.update_settings, progress=_("Saving"),
                     success=_("Settings saved") + ". " + _("Restart the app to apply them."),
                     disable=[self.save_button, self.cancel_button], on_success=saved, **values)
