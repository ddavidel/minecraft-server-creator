"""
Vector icons (QtAwesome, Material Design Icons ``mdi6``).

Code uses Material icon names (``play_arrow``,
``stop``, ``folder``...); :data:`ICON_MAP` translates them to MDI names. Any
other name is passed to QtAwesome as ``mdi6.<name>``.
"""

from __future__ import annotations

from functools import cache

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon

from mcsc_gui.ui.theme.tokens import TOKENS

ICON_MAP: dict[str, str] = {
    # Material icon names
    "play_arrow": "play",
    "stop": "stop",
    "folder": "folder-outline",
    "tune": "tune-variant",
    "delete": "delete-outline",
    "terminal": "console",
    "arrow_back": "arrow-left",
    "arrow_back_ios_new": "arrow-left",
    "add": "plus",
    "add_circle": "plus-circle-outline",
    "space_dashboard": "view-dashboard-outline",
    "download": "download",
    "settings": "cog-outline",
    "remove": "window-minimize",
    "maximize": "window-maximize",
    "restore": "window-restore",
    "close": "close",
    "check": "check",
    "error": "alert-circle-outline",
    "warning": "alert-outline",
    "info": "information-outline",
    "success": "check-circle-outline",
    "memory": "chip",
    "donut_large": "memory",
    "disk_read": "download-outline",
    "disk_write": "upload-outline",
    "edit_note": "file-document-edit-outline",
    "save": "content-save-outline",
    "search": "magnify",
    "server": "server-outline",
    "splitscreen": "server-network",
    "restart": "restart",
    "edit": "pencil-outline",
    "shortcut": "monitor-arrow-down",
}

ICON_SIZE = QSize(18, 18)


def icon_name(name: str) -> str:
    """The QtAwesome name for ``name``."""
    if "." in name:
        return name
    return "mdi6." + ICON_MAP.get(name, name)


@cache
def _icon(name: str, color: str, disabled: str, active: str | None) -> QIcon:
    import qtawesome as qta  # pylint: disable=import-outside-toplevel  # needs a QApplication

    options = {"color": color, "color_disabled": disabled}
    if active:
        options["color_active"] = active
    return qta.icon(icon_name(name), **options)


def icon(name: str, color: str | None = None, *, active: str | None = None) -> QIcon:
    """A themed vector icon. ``color`` defaults to the text color."""
    p = TOKENS.palette
    return _icon(name, color or p.text, p.text_disabled, active)
