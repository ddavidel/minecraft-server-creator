"""Statistic card: icon, caption, value and a sparkline (FR-026)."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from mcsc_gui.ui.theme.icons import icon
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.card import Card
from mcsc_gui.ui.widgets.common import label
from mcsc_gui.ui.widgets.sparkline import Sparkline


HINT_SIZE = 14


class StatTile(Card):
    """With ``row=True`` the sparkline sits right of the value (a wide, short tile).

    With ``clickable=True`` the tile is a button (:attr:`clicked`): a trend icon
    shows in its header while hovered or focused.
    """

    def __init__(self, icon_name: str, caption: str, unit: str = "",
                 color: str | None = None, parent: QWidget | None = None, *,
                 row: bool = False, clickable: bool = False) -> None:
        super().__init__(parent, clickable=clickable, padding=TOKENS.spacing.md)
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
        # Outside the layouts, in the top-right corner: showing it moves nothing
        self.hint_icon = QLabel(self)
        self.hint_icon.setPixmap(icon("trend", TOKENS.palette.text).pixmap(HINT_SIZE, HINT_SIZE))
        self.hint_icon.setFixedSize(HINT_SIZE, HINT_SIZE)
        self.hint_icon.setVisible(False)

        self.value_label = label("—", "title")
        if not clickable:  # selecting the text would swallow the click
            self.value_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
        self.sparkline = Sparkline(color=color, parent=self)

        if row:
            line = QHBoxLayout()
            line.setSpacing(TOKENS.spacing.md)
            texts = QVBoxLayout()
            texts.setSpacing(TOKENS.spacing.xs)
            texts.addLayout(head)
            texts.addWidget(self.value_label)
            line.addLayout(texts)
            self.sparkline.setMinimumHeight(36)
            line.addWidget(self.sparkline, 1, Qt.AlignmentFlag.AlignVCenter)
            self.layout_.addLayout(line)
        else:
            self.layout_.addLayout(head)
            self.layout_.addWidget(self.value_label)
            self.layout_.addWidget(self.sparkline)
        self.setAccessibleName(caption)

    def _show_hint(self, show: bool) -> None:
        if self._clickable:
            self.hint_icon.setVisible(show)
            self.hint_icon.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        inset = TOKENS.spacing.sm
        self.hint_icon.move(self.width() - HINT_SIZE - inset, inset)

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt API
        self._show_hint(True)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt API
        self._show_hint(self.hasFocus())
        super().leaveEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._show_hint(True)
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._show_hint(self.underMouse())
        super().focusOutEvent(event)

    def set_text(self, text: str | None, history: Iterable[float] = ()) -> None:
        """Show a preformatted value (``None``: the empty value)."""
        self.value_label.setText("—" if text is None else text)
        self.sparkline.set_values(history)

    def set_value(self, value: float | None, history: Iterable[float] = ()) -> None:
        if value is None:
            self.value_label.setText("—")
        else:
            text = f"{value:,.0f}" if value >= 100 else f"{value:,.1f}"
            self.value_label.setText(f"{text} {self.unit}".strip())
        self.sparkline.set_values(history)
