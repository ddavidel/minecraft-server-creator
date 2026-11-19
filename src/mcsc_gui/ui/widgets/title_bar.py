"""Custom title bar for the frameless window (FR-021)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QWidget

from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.theme.icons import icon
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.common import button, icon_button, label


def start_window_move(widget: QWidget, event: QMouseEvent) -> bool:
    """Let the OS move the window (keeps Windows snap). True if handled."""
    if event.button() != Qt.MouseButton.LeftButton:
        return False
    handle = widget.window().windowHandle()
    if handle is not None and handle.startSystemMove():
        return True
    return False


class TitleBar(QFrame):
    """Drag area, back button, page title and the window buttons."""

    back_requested = Signal()
    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent: QWidget | None = None, *, window_buttons: bool = True,
                 maximizable: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(TOKENS.title_bar_height)
        self._maximizable = maximizable

        layout = QHBoxLayout(self)
        layout.setContentsMargins(TOKENS.spacing.md, 0, TOKENS.spacing.sm, 0)
        layout.setSpacing(TOKENS.spacing.sm)

        self.back_button = icon_button("arrow_back", _("Back") + " (Alt+←)")
        self.back_button.clicked.connect(self.back_requested)
        self.back_button.hide()
        layout.addWidget(self.back_button)

        self.title_label = label("", "title")
        self.title_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(self.title_label, 1)

        # Free slot for page actions (right side, before the window buttons)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(TOKENS.spacing.xs)
        layout.addLayout(self.actions)

        self.minimize_button = button("", "remove", variant="window", tooltip=_("Minimize"))
        self.maximize_button = button("", "maximize", variant="window", tooltip=_("Maximize"))
        self.close_button = button("", "close", variant="window", tooltip=_("Close"))
        self.close_button.setProperty("tone", "danger")
        for btn in (self.minimize_button, self.maximize_button, self.close_button):
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            layout.addWidget(btn)
        self.minimize_button.clicked.connect(self.minimize_requested)
        self.maximize_button.clicked.connect(self.maximize_requested)
        self.close_button.clicked.connect(self.close_requested)

        self.set_window_buttons_visible(window_buttons)

    def set_window_buttons_visible(self, visible: bool) -> None:
        self.minimize_button.setVisible(visible)
        self.maximize_button.setVisible(visible and self._maximizable)
        self.close_button.setVisible(visible)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_back_visible(self, visible: bool) -> None:
        self.back_button.setVisible(visible)

    def set_maximized(self, maximized: bool) -> None:
        self.maximize_button.setIcon(icon("restore" if maximized else "maximize"))
        self.maximize_button.setToolTip(_("Restore") if maximized else _("Maximize"))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if start_window_move(self, event):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton and self._maximizable \
                and self.maximize_button.isVisible():
            self.maximize_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
