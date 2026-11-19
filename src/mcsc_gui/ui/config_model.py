"""
Key/value model for the config editor.

Converts the data read by ``MinecraftServer.read_config`` (a flat ``dict[str, str]``
for ``.properties``, nested dicts/lists for YAML) to a two-column
``QStandardItemModel`` and back. Each value item remembers its type, which picks
the editor (checkbox for booleans, validated input for numbers).
"""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import QModelIndex, QRegularExpression, Qt
from PySide6.QtGui import QFont, QRegularExpressionValidator, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QLineEdit, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from mcsc_gui.core.translations import translate as _

TYPE_ROLE = Qt.ItemDataRole.UserRole + 1
KEY_ROLE = Qt.ItemDataRole.UserRole + 2
ORIGINAL_ROLE = Qt.ItemDataRole.UserRole + 3

DICT, LIST, BOOL, INT, FLOAT, STR, NULL = "dict", "list", "bool", "int", "float", "str", "null"

_INT = re.compile(r"^-?\d+$")
_FLOAT = re.compile(r"^-?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?$")


def infer_property(value: str) -> Any:
    """Typed value of a ``.properties`` string (only when it round-trips exactly)."""
    if value in ("true", "false"):
        return value == "true"
    if _INT.match(value) and str(int(value)) == value:
        return int(value)
    return value


def type_of(value: Any) -> str:
    if isinstance(value, dict):
        return DICT
    if isinstance(value, list):
        return LIST
    if isinstance(value, bool):
        return BOOL
    if isinstance(value, int):
        return INT
    if isinstance(value, float):
        return FLOAT
    if value is None:
        return NULL
    return STR


def is_flat(data: Any) -> bool:
    return isinstance(data, dict) and not any(isinstance(v, (dict, list)) for v in data.values())


def _value_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, dict):
        return _("{count} keys", count=len(value))
    if isinstance(value, list):
        return _("{count} items", count=len(value))
    return str(value)


def _make_value_item(value: Any) -> QStandardItem:
    kind = type_of(value)
    item = QStandardItem()
    item.setData(kind, TYPE_ROLE)
    item.setData(value if kind not in (DICT, LIST) else None, ORIGINAL_ROLE)
    if kind == BOOL:
        item.setCheckable(True)
        item.setEditable(False)
        item.setCheckState(Qt.CheckState.Checked if value else Qt.CheckState.Unchecked)
        item.setText(_value_text(value))
    elif kind in (DICT, LIST):
        item.setEditable(False)
        item.setText(_value_text(value))
        item.setForeground(Qt.GlobalColor.gray)
    else:
        item.setText(_value_text(value))
    return item


def _append(parent: QStandardItem, key: Any, value: Any) -> None:
    key_item = QStandardItem(str(key) if not isinstance(key, int) else f"[{key}]")
    key_item.setEditable(False)
    key_item.setData(key, KEY_ROLE)
    value_item = _make_value_item(value)
    if isinstance(value, dict):
        for k, v in value.items():
            _append(key_item, k, v)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _append(key_item, i, v)
    parent.appendRow([key_item, value_item])


def build_model(data: Any, *, properties: bool = False) -> QStandardItemModel:
    """Model for ``data``; with ``properties=True`` string values get their inferred type."""
    model = QStandardItemModel()
    model.setHorizontalHeaderLabels([_("Key"), _("Value")])
    if isinstance(data, dict):
        root = model.invisibleRootItem()
        for key, value in data.items():
            if properties and isinstance(value, str):
                value = infer_property(value)
            _append(root, key, value)
    return model


def add_entry(model: QStandardItemModel, key: str, value: str = "") -> QModelIndex:
    """Append a new top-level string entry with an editable key."""
    key_item = QStandardItem(key)
    key_item.setData(key, KEY_ROLE)
    key_item.setEditable(True)
    value_item = _make_value_item(value)
    model.invisibleRootItem().appendRow([key_item, value_item])
    return key_item.index()


def _parse(kind: str, text: str, original: Any) -> Any:
    text = text.strip() if kind in (INT, FLOAT) else text
    if kind == INT:
        try:
            return int(text)
        except ValueError:
            return original
    if kind == FLOAT:
        try:
            return float(text)
        except ValueError:
            return original
    if kind == NULL:
        return None if text in ("", "null", "~") else text
    return text


def _item_value(key_item: QStandardItem, value_item: QStandardItem) -> Any:
    kind = value_item.data(TYPE_ROLE)
    if kind == DICT:
        return {_key(key_item.child(r, 0)): _item_value(key_item.child(r, 0), key_item.child(r, 1))
                for r in range(key_item.rowCount())}
    if kind == LIST:
        return [_item_value(key_item.child(r, 0), key_item.child(r, 1))
                for r in range(key_item.rowCount())]
    if kind == BOOL:
        return value_item.checkState() == Qt.CheckState.Checked
    return _parse(kind, value_item.text(), value_item.data(ORIGINAL_ROLE))


def _key(key_item: QStandardItem) -> Any:
    if key_item.isEditable():  # new entry: the key is what the user typed
        return key_item.text().strip()
    return key_item.data(KEY_ROLE)


def model_to_data(model: QStandardItemModel) -> dict[str, Any]:
    root = model.invisibleRootItem()
    data: dict[str, Any] = {}
    for row in range(root.rowCount()):
        key_item, value_item = root.child(row, 0), root.child(row, 1)
        key = _key(key_item)
        if key == "":
            continue
        data[key] = _item_value(key_item, value_item)
    return data


def mark_dirty(item: QStandardItem, dirty: bool = True) -> None:
    font = QFont(item.font())
    font.setBold(dirty)
    item.setFont(font)


class TypedDelegate(QStyledItemDelegate):
    """Editors that only accept valid ints/floats; booleans use the checkbox."""

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem,  # noqa: N802
                     index: QModelIndex) -> QWidget:
        editor = super().createEditor(parent, option, index)
        kind = index.data(TYPE_ROLE)
        if isinstance(editor, QLineEdit) and kind in (INT, FLOAT):
            pattern = _INT.pattern if kind == INT else _FLOAT.pattern
            editor.setValidator(QRegularExpressionValidator(QRegularExpression(pattern), editor))
        return editor
