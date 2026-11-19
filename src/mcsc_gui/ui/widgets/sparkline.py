"""Tiny chart of the last N samples, drawn as square bars (Voxel style)."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from mcsc_gui.ui.theme.tokens import TOKENS

BAR_WIDTH = 4
BAR_GAP = 2


class Sparkline(QWidget):
    def __init__(self, capacity: int = 60, color: str | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.capacity = capacity
        self._values: list[float] = []
        self._color = QColor(color or TOKENS.palette.accent)
        self.setMinimumHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(120, 28)

    @property
    def values(self) -> list[float]:
        return list(self._values)

    def set_values(self, values: Iterable[float]) -> None:
        self._values = [float(v) for v in values][-self.capacity:]
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        if not self._values:
            return
        painter = QPainter(self)
        w, h = self.width(), self.height()
        slots = max(1, (w + BAR_GAP) // (BAR_WIDTH + BAR_GAP))
        shown = self._values[-slots:]
        top = max(self._values) or 1.0

        # Empty slots as a faint floor, newest sample on the right edge.
        floor = QColor(TOKENS.palette.surface_sunken)
        for i in range(slots):
            x = w - (slots - i) * (BAR_WIDTH + BAR_GAP) + BAR_GAP
            painter.fillRect(QRectF(x, h - 2, BAR_WIDTH, 2), floor)

        start = slots - len(shown)
        for i, value in enumerate(shown):
            bar = max(2.0, round((value / top) * h / 2) * 2)  # snap to 2 px steps
            x = w - (slots - start - i) * (BAR_WIDTH + BAR_GAP) + BAR_GAP
            painter.fillRect(QRectF(x, h - bar, BAR_WIDTH, bar), self._color)
