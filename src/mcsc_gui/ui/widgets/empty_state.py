"""Illustrated empty state: big icon, title, text and an optional action."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from mcsc_gui.ui.theme.icons import icon
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.common import label


class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, text: str = "",
                 action: QPushButton | QWidget | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(TOKENS.spacing.md)

        art = QLabel(self)
        art.setPixmap(icon(icon_name, TOKENS.palette.accent).pixmap(72, 72))
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        art.setFixedSize(120, 120)
        p, b = TOKENS.palette, TOKENS.borders
        art.setStyleSheet(
            f"background: {p.surface_raised}; border: {b.width}px solid {p.border};"
            f" border-bottom: {b.card_bevel}px solid {p.surface_sunken}; border-radius: 0;"
        )
        layout.addWidget(art, 0, Qt.AlignmentFlag.AlignHCenter)

        self.title_label = label(title, "headline")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)
        if text:
            body = label(text, "muted", wrap=True)
            body.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body.setFixedWidth(420)  # a wrapped label needs a width to compute its height
            layout.addWidget(body, 0, Qt.AlignmentFlag.AlignHCenter)
        if action is not None:
            layout.addSpacing(TOKENS.spacing.sm)
            layout.addWidget(action, 0, Qt.AlignmentFlag.AlignHCenter)
