"""Form pieces shared by the server dialogs."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.common import label, set_prop

MAX_NAME_LENGTH = 34  # names must be shorter than 35 characters


def validate_name(name: str) -> str | None:
    """Translated validation error for a server name, ``None`` if valid."""
    name = (name or "").strip()
    if not name:
        return _("Server name can't be empty")
    if len(name) > MAX_NAME_LENGTH:
        return _("Too long!")
    return None


class Field(QWidget):
    """Caption + input + inline error message."""

    def __init__(self, caption: str, widget: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(TOKENS.spacing.xs)
        self.caption = label(caption, "caption")
        self.caption.setBuddy(widget)
        layout.addWidget(self.caption)
        self.widget = widget
        widget.setAccessibleName(caption)
        layout.addWidget(widget)
        self.error_label = label("", "error")
        self.error_label.setTextFormat(Qt.TextFormat.PlainText)
        self.error_label.hide()
        layout.addWidget(self.error_label)

    @property
    def error(self) -> str | None:
        return self.error_label.text() if self.error_label.isVisible() else None

    def set_error(self, message: str | None) -> None:
        self.error_label.setText(message or "")
        self.error_label.setVisible(bool(message))
        set_prop(self.widget, "invalid", "true" if message else "false")


def name_field(value: str = "") -> Field:
    edit = QLineEdit(value)
    edit.setPlaceholderText(_("My awesome server"))
    edit.setMaxLength(64)
    field = Field(_("Server name"), edit)

    def live_check(text: str) -> None:
        # Only the length is checked live; "empty" is reported on submit
        field.set_error(_("Too long!") if len(text.strip()) > MAX_NAME_LENGTH else None)

    edit.textChanged.connect(live_check)
    return field
