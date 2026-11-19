"""Statistic card: icon, caption, value and a sparkline (FR-026)."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from mcsc_gui.ui.theme.icons import icon
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.card import Card
from mcsc_gui.ui.widgets.common import label
from mcsc_gui.ui.widgets.sparkline import Sparkline


class StatTile(Card):
    def __init__(self, icon_name: str, caption: str, unit: str = "",
                 color: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=TOKENS.spacing.md)
        self.unit = unit
        self.setToolTip(caption)
        self.layout_.setSpacing(TOKENS.spacing.xs)
        color = color or TOKENS.palette.accent

        head = QHBoxLayout()
        head.setSpacing(TOKENS.spacing.sm)
        art = QLabel(self)
        art.setPixmap(icon(icon_name, color).pixmap(16, 16))
        head.addWidget(art)
        head.addWidget(label(caption, "caption"), 1)
        self.layout_.addLayout(head)

        self.value_label = label("—", "title")
        self.value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.layout_.addWidget(self.value_label)

        self.sparkline = Sparkline(color=color, parent=self)
        self.layout_.addWidget(self.sparkline)
        self.setAccessibleName(caption)

    def set_value(self, value: float | None, history: Iterable[float] = ()) -> None:
        if value is None:
            self.value_label.setText("—")
        else:
            text = f"{value:,.0f}" if value >= 100 else f"{value:,.1f}"
            self.value_label.setText(f"{text} {self.unit}".strip())
        self.sparkline.set_values(history)
