"""Indeterminate progress indicator: four blocks lighting up in turn (Voxel style)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from mcsc_gui.ui.theme.tokens import TOKENS

# Clockwise order of the 2x2 cells: top-left, top-right, bottom-right, bottom-left.
_CELLS = ((0, 0), (1, 0), (1, 1), (0, 1))


class Spinner(QWidget):
    """Animates while visible; costs nothing when hidden."""

    def __init__(self, size: int = 18, color: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._size = size
        self._color = QColor(color or TOKENS.palette.accent)
        self._step = 0
        self._timer = QTimer(self)
        self._timer.setInterval(140)
        self._timer.timeout.connect(self._tick)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(self._size, self._size)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._timer.stop()
        super().hideEvent(event)

    def _tick(self) -> None:
        self._step = (self._step + 1) % len(_CELLS)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        gap = max(2, self._size // 9)
        cell = (self._size - gap) / 2
        for index, (cx, cy) in enumerate(_CELLS):
            color = QColor(self._color)
            # The lit cell is full, the one before it fading, the others dim.
            distance = (self._step - index) % len(_CELLS)
            color.setAlpha({0: 255, 1: 140}.get(distance, 50))
            painter.fillRect(QRectF(cx * (cell + gap), cy * (cell + gap), cell, cell), color)
