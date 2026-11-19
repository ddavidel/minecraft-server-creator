"""Surface container with rounded corners."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from mcsc_gui.ui.theme.tokens import TOKENS


class Card(QFrame):
    """A card. With ``clickable=True`` it emits :attr:`clicked` (mouse, Enter or Space)."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None, *, clickable: bool = False,
                 raised: bool = False, padding: int | None = None) -> None:
        super().__init__(parent)
        self.setProperty("card", "raised" if raised else "true")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._clickable = clickable
        if clickable:
            self.setProperty("clickable", "true")
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        pad = TOKENS.spacing.lg if padding is None else padding
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(pad, pad, pad, pad)
        self.layout_.setSpacing(TOKENS.spacing.md)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if self._clickable and event.button() == Qt.MouseButton.LeftButton \
                and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        if self._clickable and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter,
                                               Qt.Key.Key_Space):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)
