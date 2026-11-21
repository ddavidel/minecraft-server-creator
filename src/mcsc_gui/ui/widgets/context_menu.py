"""Themed context menu whose destructive actions are drawn in the danger color."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QPaintEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QWidget, QWidgetAction

from mcsc_gui.ui.theme.icons import ICON_SIZE, icon
from mcsc_gui.ui.theme.tokens import TOKENS


class _DangerItem(QWidget):
    """Row of a danger action: icon + text, highlighted while the action is active.

    Transparent for the mouse: hover and clicks reach the menu, which handles
    them as for any other action.
    """

    def __init__(self, text: str, icon_name: str | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DangerMenuItem")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setProperty("active", "false")
        row = QHBoxLayout(self)
        # Same columns as the native items: icon at the left edge, text after it
        row.setContentsMargins(7, 6, 16, 6)
        row.setSpacing(0)
        self.icon_label = QLabel()
        self.icon_label.setObjectName("DangerMenuItemIcon")
        self.icon_label.setFixedWidth(33)
        self._icon_name = icon_name
        if icon_name:
            row.addWidget(self.icon_label)
        self.text_label = QLabel(text)
        self.text_label.setObjectName("DangerMenuItemText")
        row.addWidget(self.text_label, 1)
        self._update_icon()

    @property
    def active(self) -> bool:
        return self.property("active") == "true"

    def set_active(self, active: bool) -> None:
        if active == self.active:
            return
        self.setProperty("active", "true" if active else "false")
        for widget in (self, self.text_label):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self._update_icon()

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().changeEvent(event)
        if event.type() == event.Type.EnabledChange:
            self._update_icon()

    def _update_icon(self) -> None:
        if not self._icon_name:
            return
        p = TOKENS.palette
        if not self.isEnabled():
            color = p.text_disabled
        elif self.active:
            color = "#ffffff"
        else:
            color = p.danger_text
        self.icon_label.setPixmap(icon(self._icon_name, color).pixmap(ICON_SIZE))


class ContextMenu(QMenu):
    """A :class:`QMenu` with :meth:`add_danger_action` (red text and icon).

    Style sheets can't target a single :class:`QAction`, so a danger action is a
    :class:`QWidgetAction` whose row is styled as ``#DangerMenuItem``; it still
    emits ``triggered`` on click and Enter like any other action.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ContextMenu")
        self._danger_items: dict[QAction, _DangerItem] = {}

    def add_action(self, text: str, icon_name: str | None = None) -> QAction:
        action = self.addAction(text)
        if icon_name:
            action.setIcon(icon(icon_name))
        return action

    def add_danger_action(self, text: str, icon_name: str | None = None) -> QAction:
        action = QWidgetAction(self)
        action.setText(text)
        item = _DangerItem(text, icon_name)
        action.setDefaultWidget(item)
        self.addAction(action)
        self._danger_items[action] = item
        return action

    def danger_item(self, action: QAction) -> _DangerItem | None:
        return self._danger_items.get(action)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt API
        # The menu repaints whenever the active action changes (mouse or keyboard)
        active = self.activeAction()
        for action, item in self._danger_items.items():
            item.setEnabled(action.isEnabled())
            item.set_active(action is active and action.isEnabled())
        super().paintEvent(event)
