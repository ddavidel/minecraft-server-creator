"""Dashboard card of a server: name, type/version, state, Start/Stop and a context menu."""

from __future__ import annotations

import logging

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QContextMenuEvent, QKeyEvent
from PySide6.QtWidgets import QHBoxLayout, QMenu, QWidget

from mcsc import MinecraftServer

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.theme.icons import ICON_SIZE, icon
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.card import Card
from mcsc_gui.ui.widgets.common import button, label
from mcsc_gui.ui.widgets.context_menu import ContextMenu
from mcsc_gui.ui.widgets.status_badge import StatusBadge


logger = logging.getLogger(__name__)


class ServerCard(Card):
    open_requested = Signal(str)  # server_id
    start_requested = Signal(str)
    stop_requested = Signal(str)
    edit_requested = Signal(str)
    clone_requested = Signal(str)
    delete_requested = Signal(str)

    MIN_WIDTH = 300

    def __init__(self, server: MinecraftServer, parent: QWidget | None = None) -> None:
        super().__init__(parent, clickable=True)
        self.server = server
        self._menu: QMenu | None = None
        self.setMinimumWidth(self.MIN_WIDTH)
        self.clicked.connect(lambda: self.open_requested.emit(self.server.id))

        top = QHBoxLayout()
        top.setSpacing(TOKENS.spacing.sm)
        self.name_label = label("", "title")
        self.name_label.setTextFormat(Qt.TextFormat.PlainText)
        top.addWidget(self.name_label, 1)
        self.auto_start_icon = label()
        self.auto_start_icon.setPixmap(
            icon("auto_start", TOKENS.palette.text_muted).pixmap(ICON_SIZE))
        self.auto_start_icon.setToolTip(_("Starts automatically when the app opens"))
        top.addWidget(self.auto_start_icon, 0, Qt.AlignmentFlag.AlignVCenter)
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
        self.badge.set_activity(sm.activity_label(self.server))
        self.auto_start_icon.setVisible(sm.server_auto_start(self.server))
        self.start_button.setEnabled(sm.can_start(self.server))
        self.stop_button.setEnabled(sm.can_stop(self.server))
        self.setAccessibleName(f"{config.name}, {self.badge.text}")

    # ---------------------------------------------------------- context menu

    def build_menu(self) -> ContextMenu:
        """Edit / Clone / Delete menu, enabled from the server's current state."""
        menu = ContextMenu(self)
        menu.setToolTipsVisible(True)
        server_id = self.server.id
        edit = menu.add_action(_("Edit"), "edit")
        edit.triggered.connect(lambda: self.edit_requested.emit(server_id))
        clone = menu.add_action(_("Clone"), "content_copy")
        clone.triggered.connect(lambda: self.clone_requested.emit(server_id))
        auto_start = menu.add_action(_("Start when the app opens"), "auto_start")
        auto_start.setCheckable(True)
        auto_start.setChecked(sm.server_auto_start(self.server))
        auto_start.toggled.connect(self.set_auto_start)
        menu.addSeparator()
        delete = menu.add_danger_action(_("Delete"), "delete")
        delete.triggered.connect(lambda: self.delete_requested.emit(server_id))
        for action, reason in ((clone, sm.clone_block_reason(self.server)),
                               (delete, sm.delete_block_reason(self.server))):
            action.setEnabled(reason is None)
            action.setToolTip(reason or "")
        return menu

    def set_auto_start(self, enabled: bool) -> None:
        """Turn auto start on/off from the menu (the card refreshes on server_updated)."""
        try:
            sm.set_server_auto_start(self.server, enabled)
        except OSError:
            logger.exception("Can't save the auto start preference")

    @property
    def menu(self) -> QMenu | None:
        """The open context menu, ``None`` if it's closed."""
        return self._menu

    def show_menu(self, global_pos: QPoint | None = None) -> QMenu:
        """Open the context menu at ``global_pos`` (below the card's title by default)."""
        if self._menu is not None:  # e.g. Shift+F10 also arrives as a context menu event
            return self._menu
        menu = self.build_menu()
        self._menu = menu

        def closed() -> None:
            self._menu = None
            menu.deleteLater()  # after ``triggered``: deleteLater runs in the event loop

        menu.aboutToHide.connect(closed)
        if global_pos is None:
            anchor = QPoint(TOKENS.spacing.lg, self.name_label.geometry().bottom())
            global_pos = self.mapToGlobal(anchor)
        menu.popup(global_pos)
        return menu

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802 - Qt API
        # Mouse: at the cursor. Keyboard (Menu key, Shift+F10): anchored to the card.
        if event.reason() == QContextMenuEvent.Reason.Mouse:
            self.show_menu(event.globalPos())
        else:
            self.show_menu()
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        shift_f10 = (event.key() == Qt.Key.Key_F10
                     and event.modifiers() == Qt.KeyboardModifier.ShiftModifier)
        if shift_f10 or event.key() == Qt.Key.Key_Menu:
            self.show_menu()
            event.accept()
            return
        super().keyPressEvent(event)
