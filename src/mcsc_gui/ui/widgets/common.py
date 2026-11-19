"""Small helpers to build themed widgets consistently."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QSizePolicy, QWidget

from mcsc_gui.ui.theme.icons import icon


def repolish(widget: QWidget) -> None:
    """Re-apply the stylesheet after a dynamic property changed."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_prop(widget: QWidget, name: str, value) -> None:
    """Set a dynamic style property and refresh the widget's style."""
    if widget.property(name) != value:
        widget.setProperty(name, value)
        repolish(widget)


def button(
    text: str = "",
    icon_name: str | None = None,
    *,
    variant: str = "secondary",
    tooltip: str | None = None,
    parent: QWidget | None = None,
    icon_color: str | None = None,
) -> QPushButton:
    """A themed push button (``variant``: primary, secondary, danger, ghost, icon, nav)."""
    btn = QPushButton(text, parent)
    btn.setProperty("variant", variant)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if icon_name:
        from mcsc_gui.ui.theme.tokens import TOKENS  # pylint: disable=import-outside-toplevel

        color = icon_color
        if color is None:
            color = {
                "primary": TOKENS.palette.text_on_accent,
                "danger": "#ffffff",
            }.get(variant)
        btn.setIcon(icon(icon_name, color))
        btn.setIconSize(QSize(18, 18))
    if tooltip:
        btn.setToolTip(tooltip)
        btn.setAccessibleName(tooltip)
    elif text:
        btn.setAccessibleName(text)
    return btn


def icon_button(icon_name: str, tooltip: str, *, parent: QWidget | None = None,
                color: str | None = None) -> QPushButton:
    """A square, borderless icon button with a tooltip (required for accessibility)."""
    return button("", icon_name, variant="icon", tooltip=tooltip, parent=parent, icon_color=color)


def label(text: str = "", role: str | None = None, *, parent: QWidget | None = None,
          wrap: bool = False) -> QLabel:
    """A themed label (``role``: display, headline, title, muted, caption, error, overline)."""
    lbl = QLabel(text, parent)
    if role:
        lbl.setProperty("role", role)
    if wrap:
        lbl.setWordWrap(True)
    return lbl


def separator(parent: QWidget | None = None) -> QFrame:
    line = QFrame(parent)
    line.setObjectName("Separator")
    line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return line
