"""RAM slider with the current value and a "suggested" marker."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QSlider, QVBoxLayout, QWidget

from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.common import label


class _MarkedSlider(QSlider):
    """
    Slider drawn as a row of blocks, one per GB (Voxel style).

    Filled blocks up to the value; the current block is outlined, and a small
    square under a block marks the suggested value. Keyboard and wheel work as
    in any QSlider; a click or drag jumps straight to the block under the mouse.
    """

    MAX_CELLS = 32
    CELL_HEIGHT = 16
    GAP = 3

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.suggested: int | None = None
        self.setMinimumHeight(self.CELL_HEIGHT + 12)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # ------------------------------------------------------------ geometry

    def _cells(self) -> int:
        return max(1, min(self.MAX_CELLS, self.maximum() - self.minimum() + 1))

    def _cell_rect(self, index: int) -> QRectF:
        cells = self._cells()
        width = (self.width() - 4 - self.GAP * (cells - 1)) / cells
        return QRectF(2 + index * (width + self.GAP), 2, width, self.CELL_HEIGHT)

    def _cell_for(self, value: int) -> int:
        """Index of the block that shows ``value``."""
        span = self.maximum() - self.minimum()
        if span <= 0:
            return 0
        return round((value - self.minimum()) / span * (self._cells() - 1))

    def _value_at(self, x: float) -> int:
        span = self.maximum() - self.minimum()
        ratio = min(1.0, max(0.0, (x - 2) / max(1, self.width() - 4)))
        return self.minimum() + round(ratio * span)

    # --------------------------------------------------------------- mouse

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            self.setSliderDown(True)
            self.setValue(self._value_at(event.position().x()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self.isSliderDown():
            self.setValue(self._value_at(event.position().x()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self.isSliderDown():
            self.setSliderDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # --------------------------------------------------------------- paint

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        p = TOKENS.palette
        painter = QPainter(self)
        enabled = self.isEnabled()
        filled = QColor(p.accent if enabled else p.text_disabled)
        current = self._cell_for(self.value())

        for index in range(self._cells()):
            rect = self._cell_rect(index)
            painter.fillRect(rect, filled if index <= current else QColor(p.surface_sunken))

        # Outline on the current block (accent edge when focused).
        rect = self._cell_rect(current).adjusted(-1, -1, 1, 1)
        outline = QColor(p.text if not self.hasFocus() else p.accent_hover)
        painter.setPen(QPen(outline, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap,
                            Qt.PenJoinStyle.MiterJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)

        if self.suggested is not None and self.minimum() <= self.suggested <= self.maximum():
            cell = self._cell_rect(self._cell_for(self.suggested))
            marker = QRectF(cell.center().x() - 3, cell.bottom() + 5, 6, 6)
            painter.fillRect(marker, QColor(p.warning))


class RamSlider(QWidget):
    valueChanged = Signal(int)  # noqa: N815 - Qt naming

    def __init__(self, maximum: int, value: int, suggested: int | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(TOKENS.spacing.xs)

        head = QHBoxLayout()
        head.addWidget(label(_("Dedicated RAM"), "title"), 1)
        self.value_label = label("", "title")
        self.value_label.setStyleSheet(f"color: {TOKENS.palette.accent};")
        head.addWidget(self.value_label)
        layout.addLayout(head)

        self.slider = _MarkedSlider(self)
        self.slider.setRange(1, max(1, maximum))
        self.slider.setPageStep(1)
        self.slider.suggested = suggested
        self.slider.setAccessibleName(_("Dedicated RAM"))
        self.slider.valueChanged.connect(self._on_change)
        layout.addWidget(self.slider)

        scale = QHBoxLayout()
        scale.addWidget(label("1 GB", "caption"))
        scale.addStretch(1)
        if suggested is not None:
            hint = label(_("Suggested for this device: {value} GB", value=suggested), "caption")
            scale.addWidget(hint)
            scale.addStretch(1)
        scale.addWidget(label(f"{max(1, maximum)} GB", "caption"))
        layout.addLayout(scale)

        self.slider.setValue(min(max(1, value), self.slider.maximum()))
        self._on_change(self.slider.value())

    def value(self) -> int:
        return self.slider.value()

    def setValue(self, value: int) -> None:  # noqa: N802 - Qt naming
        self.slider.setValue(value)

    def maximum(self) -> int:
        return self.slider.maximum()

    def _on_change(self, value: int) -> None:
        self.value_label.setText(f"{value} GB")
        self.slider.setToolTip(f"{value} GB")
        self.valueChanged.emit(value)
