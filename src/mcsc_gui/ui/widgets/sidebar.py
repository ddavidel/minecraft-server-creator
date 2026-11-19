"""Navigation sidebar: logo, main entries, updates and settings at the bottom."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.theme.icons import icon
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.common import button, label, set_prop
from mcsc_gui.ui.widgets.title_bar import start_window_move
from mcsc_gui.utils import get_static_path


class _Logo(QWidget):
    """Logo area; also a drag handle for the frameless window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(TOKENS.spacing.sm, TOKENS.spacing.md, 0, TOKENS.spacing.md)
        layout.setSpacing(TOKENS.spacing.sm)
        logo = QLabel(self)
        logo.setToolTip("Minecraft Server Creator")
        logo.setAccessibleName("Minecraft Server Creator")
        pixmap = QPixmap(str(get_static_path("logo.png")))
        if not pixmap.isNull():
            dpr = self.devicePixelRatioF()
            width = TOKENS.sidebar_width - 2 * TOKENS.spacing.md - TOKENS.spacing.lg
            scaled = pixmap.scaledToWidth(int(width * dpr), Qt.TransformationMode.SmoothTransformation)
            scaled.setDevicePixelRatio(dpr)
            logo.setPixmap(scaled)
        else:
            logo.setText("Minecraft Server Creator")
        layout.addWidget(logo)
        layout.addStretch(1)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if not start_window_move(self, event):
            super().mousePressEvent(event)


class Sidebar(QFrame):
    dashboard_clicked = Signal()
    new_server_clicked = Signal()
    updates_clicked = Signal()
    settings_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(TOKENS.sidebar_width)
        s = TOKENS.spacing

        layout = QVBoxLayout(self)
        layout.setContentsMargins(s.md, s.sm, s.md, s.lg)
        layout.setSpacing(s.xs)
        layout.addWidget(_Logo(self))
        layout.addSpacing(s.md)

        self.new_server_button = button(_("New server"), "add", variant="primary",
                                        tooltip=_("New server") + " (Ctrl+N)")
        self.new_server_button.clicked.connect(self.new_server_clicked)
        layout.addWidget(self.new_server_button)
        layout.addSpacing(s.md)

        layout.addWidget(label(_("MENU"), "overline"))
        self.dashboard_button = self._nav(_("Dashboard"), "space_dashboard")
        self.dashboard_button.setCheckable(True)
        self.dashboard_button.clicked.connect(self.dashboard_clicked)
        layout.addWidget(self.dashboard_button)

        self._group = QButtonGroup(self)
        self._group.setExclusive(False)
        self._group.addButton(self.dashboard_button)

        layout.addStretch(1)

        self.updates_button = self._nav(_("Check for updates"), "download")
        self.updates_button.clicked.connect(self.updates_clicked)
        layout.addWidget(self.updates_button)
        self.settings_button = self._nav(_("App Settings"), "settings")
        self.settings_button.clicked.connect(self.settings_clicked)
        layout.addWidget(self.settings_button)

    def _nav(self, text: str, icon_name: str):
        btn = button(text, icon_name, variant="nav", icon_color=TOKENS.palette.text_muted)
        btn.setIcon(icon(icon_name, TOKENS.palette.text_muted, active=TOKENS.palette.text))
        return btn

    def set_active(self, entry: str | None) -> None:
        """Highlight ``"dashboard"`` (or nothing for inner pages)."""
        self.dashboard_button.setChecked(entry == "dashboard")
        color = TOKENS.palette.accent if entry == "dashboard" else TOKENS.palette.text_muted
        self.dashboard_button.setIcon(icon("space_dashboard", color))

    def set_update_available(self, available: bool) -> None:
        set_prop(self.updates_button, "highlight", "true" if available else "false")
        self.updates_button.setText(_("Update available") if available else _("Check for updates"))
        color = TOKENS.palette.warning_text if available else TOKENS.palette.text_muted
        self.updates_button.setIcon(icon("download", color))
