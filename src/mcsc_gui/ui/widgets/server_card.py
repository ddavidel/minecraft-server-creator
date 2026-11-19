"""Dashboard card of a server: name, type/version, state and Start/Stop."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from mcsc import MinecraftServer

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.card import Card
from mcsc_gui.ui.widgets.common import button, label
from mcsc_gui.ui.widgets.status_badge import StatusBadge


class ServerCard(Card):
    open_requested = Signal(str)  # server_id
    start_requested = Signal(str)
    stop_requested = Signal(str)

    MIN_WIDTH = 300

    def __init__(self, server: MinecraftServer, parent: QWidget | None = None) -> None:
        super().__init__(parent, clickable=True)
        self.server = server
        self.setMinimumWidth(self.MIN_WIDTH)
        self.clicked.connect(lambda: self.open_requested.emit(self.server.id))

        top = QHBoxLayout()
        top.setSpacing(TOKENS.spacing.sm)
        self.name_label = label("", "title")
        self.name_label.setTextFormat(Qt.TextFormat.PlainText)
        top.addWidget(self.name_label, 1)
        self.badge = StatusBadge(server.state)
        top.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)
        self.layout_.addLayout(top)

        self.details_label = label("", "mono")
        self.layout_.addWidget(self.details_label)
        self.layout_.addStretch(1)

        actions = QHBoxLayout()
        actions.setSpacing(TOKENS.spacing.sm)
        self.start_button = button(_("Start"), "play_arrow", variant="primary")
        self.stop_button = button(_("Stop"), "stop")
        self.start_button.clicked.connect(lambda: self.start_requested.emit(self.server.id))
        self.stop_button.clicked.connect(lambda: self.stop_requested.emit(self.server.id))
        actions.addWidget(self.start_button)
        actions.addWidget(self.stop_button)
        actions.addStretch(1)
        self.layout_.addLayout(actions)

        self.refresh()

    def refresh(self) -> None:
        """Re-read name, state and button availability from the server."""
        config = self.server.config
        self.name_label.setText(config.name)
        self.name_label.setToolTip(self.server.id)
        self.details_label.setText(
            f"{config.server_type.label} · {config.version} · {config.ram_gb} GB RAM"
        )
        self.badge.set_state(self.server.state)
        self.start_button.setEnabled(sm.can_start(self.server))
        self.stop_button.setEnabled(sm.can_stop(self.server))
        self.setAccessibleName(f"{config.name}, {self.badge.text}")
