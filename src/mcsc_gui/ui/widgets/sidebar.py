"""Navigation sidebar: logo, contextual entries, updates and settings at the bottom.

On the dashboard it shows the app menu ("New server", "Dashboard"); on a server's
pages it shows that server (name, state) and its sections.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mcsc import MinecraftServer

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.navigator import BACKUPS, CONFIGURATION, CONSOLE, SERVER, SERVER_SETTINGS
from mcsc_gui.ui.theme.icons import icon
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.card import Card
from mcsc_gui.ui.widgets.common import button, label, set_prop
from mcsc_gui.ui.widgets.status_badge import StatusBadge
from mcsc_gui.ui.widgets.title_bar import start_window_move
from mcsc_gui.utils import get_static_path

# (section, label, icon) of the server menu, in order
SERVER_NAV: tuple[tuple[str, str, str], ...] = (
    (SERVER, "Overview", "view-dashboard-outline"),
    (CONSOLE, "Console", "terminal"),
    (CONFIGURATION, "Configuration", "file-cog-outline"),
    (BACKUPS, "Backups", "archive-outline"),
    (SERVER_SETTINGS, "Settings", "tune"),
)


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
    section_clicked = Signal(str, str)  # server_id, section
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

        # The top part is contextual: the app menu, or the sections of the open server
        self._modes = QStackedWidget(self)

        app_menu = QWidget()
        app_layout = QVBoxLayout(app_menu)
        app_layout.setContentsMargins(0, 0, 0, 0)
        app_layout.setSpacing(s.xs)
        self.new_server_button = button(_("New server"), "add", variant="primary",
                                        tooltip=_("New server") + " (Ctrl+N)")
        self.new_server_button.clicked.connect(self.new_server_clicked)
        app_layout.addWidget(self.new_server_button)
        app_layout.addSpacing(s.md)
        app_layout.addWidget(label(_("MENU"), "overline"))
        self.dashboard_button = self._nav(_("Dashboard"), "space_dashboard")
        self.dashboard_button.setCheckable(True)
        self.dashboard_button.clicked.connect(self.dashboard_clicked)
        app_layout.addWidget(self.dashboard_button)
        app_layout.addStretch(1)
        self._modes.addWidget(app_menu)

        self._group = QButtonGroup(self)
        self._group.setExclusive(False)
        self._group.addButton(self.dashboard_button)

        server_menu = QWidget()
        server_layout = QVBoxLayout(server_menu)
        server_layout.setContentsMargins(0, 0, 0, 0)
        server_layout.setSpacing(s.xs)
        self.back_button = self._nav(_("Dashboard"), "arrow_back")
        self.back_button.setToolTip(_("Back to the dashboard"))
        self.back_button.clicked.connect(self.dashboard_clicked)
        server_layout.addWidget(self.back_button)
        server_layout.addSpacing(s.sm)

        self.server_card = Card(padding=s.md)
        self.server_card.layout_.setSpacing(s.xs)
        self.server_name = label("", "title", wrap=True)
        self.server_name.setTextFormat(Qt.TextFormat.PlainText)
        self.server_card.layout_.addWidget(self.server_name)
        self.server_badge = StatusBadge()
        self.server_card.layout_.addWidget(self.server_badge, 0, Qt.AlignmentFlag.AlignLeft)
        self.server_details = label("", "mono")
        self.server_card.layout_.addWidget(self.server_details)
        server_layout.addWidget(self.server_card)
        server_layout.addSpacing(s.md)

        server_layout.addWidget(label(_("SERVER"), "overline"))
        self.section_buttons: dict[str, QPushButton] = {}
        for section, text, icon_name in SERVER_NAV:
            btn = self._nav(_(text), icon_name)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _c=False, sec=section: self._on_section_clicked(sec))
            server_layout.addWidget(btn)
            self.section_buttons[section] = btn
        server_layout.addStretch(1)
        self._modes.addWidget(server_menu)

        self.server: MinecraftServer | None = None
        self.section: str | None = None
        layout.addWidget(self._modes, 1)

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

    # --------------------------------------------------------- server menu

    @property
    def showing_server(self) -> bool:
        return self._modes.currentIndex() == 1

    def show_app_menu(self) -> None:
        self.server = None
        self.section = None
        self._modes.setCurrentIndex(0)

    def show_server(self, server: MinecraftServer, section: str) -> None:
        """Show the sections of ``server``, with ``section`` highlighted."""
        self.server = server
        self.section = section
        self._modes.setCurrentIndex(1)
        for sec, _text, icon_name in SERVER_NAV:
            btn = self.section_buttons[sec]
            active = sec == section
            btn.setChecked(active)
            btn.setIcon(icon(icon_name, TOKENS.palette.accent if active
                             else TOKENS.palette.text_muted))
        self.refresh_server()

    def refresh_server(self, server_id: str | None = None) -> None:
        """Re-read name, state and version of the shown server."""
        server = self.server
        if server is None or (server_id is not None and server_id != server.id):
            return
        config = server.config
        self.server_name.setText(config.name)
        self.server_badge.set_state(server.state)
        self.server_badge.set_activity(sm.activity_label(server))
        self.server_details.setText(f"{config.server_type.label} {config.version}")

    def _on_section_clicked(self, section: str) -> None:
        if self.server is None:
            return
        # Keep the highlight on the current section until the navigation happens
        self.section_buttons[section].setChecked(section == self.section)
        self.section_clicked.emit(self.server.id, section)

    def set_update_available(self, available: bool) -> None:
        set_prop(self.updates_button, "highlight", "true" if available else "false")
        self.updates_button.setText(_("Update available") if available else _("Check for updates"))
        color = TOKENS.palette.warning_text if available else TOKENS.palette.text_muted
        self.updates_button.setIcon(icon("download", color))
