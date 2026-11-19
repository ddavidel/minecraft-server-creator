"""Editor of a server config file (US5)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QStackedLayout,
    QTableView,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from mcsc import MinecraftServer

from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui import config_model as cm
from mcsc_gui.ui.tasks import run_blocking
from mcsc_gui.ui.theme.icons import icon
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.common import button, label, set_prop
from mcsc_gui.ui.widgets.overlay_dialog import MessageDialog
from mcsc_gui.ui.widgets.spinner import Spinner


class ConfigEditorPage(QWidget):
    title_changed = Signal(str)
    saved = Signal()

    def __init__(self, server: MinecraftServer, filename: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")
        self.server = server
        self.filename = filename
        self.properties = PurePosixPath(filename).suffix.lower() == ".properties"
        self._dirty = False
        self._loaded = False
        self._load_error: str | None = None
        self.model = QStandardItemModel(self)
        s = TOKENS.spacing

        root = QVBoxLayout(self)
        root.setContentsMargins(s.xxl, s.xl, s.xxl, s.xl)
        root.setSpacing(s.lg)

        header = QHBoxLayout()
        header.setSpacing(s.md)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label(filename, "headline"))
        self.status_label = label(server.name, "muted")
        titles.addWidget(self.status_label)
        header.addLayout(titles, 1)

        self.search = QLineEdit()
        self.search.setPlaceholderText(_("Search"))
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", TOKENS.palette.text_muted),
                              QLineEdit.ActionPosition.LeadingPosition)
        self.search.setFixedWidth(260)
        self.search.setAccessibleName(_("Search"))
        header.addWidget(self.search)
        self.add_button = button(_("Add entry"), "add")
        self.add_button.clicked.connect(self.add_entry)
        header.addWidget(self.add_button)
        self.save_button = button(_("Save"), "save", variant="primary",
                                  tooltip=_("Save") + " (Ctrl+S)")
        self.save_button.clicked.connect(self.save)
        header.addWidget(self.save_button)
        root.addLayout(header)

        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setRecursiveFilteringEnabled(True)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)
        self.search.textChanged.connect(self.proxy.setFilterFixedString)

        self._content = QStackedLayout()
        loading = QWidget()
        loading_layout = QHBoxLayout(loading)
        loading_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_layout.addWidget(Spinner(28))
        self._content.addWidget(loading)
        self.view: QTableView | QTreeView | None = None
        root.addLayout(self._content, 1)

        QShortcut(QKeySequence.StandardKey.Save, self, activated=self.save)
        self._update_actions()
        run_blocking(server.read_config, filename, on_success=self._loaded_data,
                     on_error=self._load_failed)

    # ---------------------------------------------------------------- loading

    @property
    def dirty(self) -> bool:
        return self._dirty

    def page_title(self) -> str:
        return f"{self.server.name} · {self.filename}"

    def _loaded_data(self, data: Any) -> None:
        self._set_data(data if isinstance(data, dict) else {})

    def _load_failed(self, error: Exception) -> None:
        # The error toast is shown by run_task; the editor stays usable (empty)
        self._load_error = str(error)
        self._set_data({})
        self.status_label.setText(_("Can't read {file}", file=self.filename))
        set_prop(self.status_label, "role", "error")

    def _set_data(self, data: dict[str, Any]) -> None:
        self.model = cm.build_model(data, properties=self.properties)
        self.model.itemChanged.connect(self._on_item_changed)
        self.proxy.setSourceModel(self.model)
        flat = cm.is_flat(data)
        view: QTableView | QTreeView
        if flat:
            view = QTableView()
            view.verticalHeader().hide()
            view.setShowGrid(False)
            view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            view.setSortingEnabled(False)
        else:
            view = QTreeView()
            view.setUniformRowHeights(True)
        view.setModel(self.proxy)
        view.setAlternatingRowColors(True)
        view.setItemDelegate(cm.TypedDelegate(view))
        view.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                             | QAbstractItemView.EditTrigger.EditKeyPressed
                             | QAbstractItemView.EditTrigger.AnyKeyPressed)
        header = view.horizontalHeader() if isinstance(view, QTableView) else view.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.resizeSection(0, 320)
        view.setAccessibleName(self.filename)
        if self.view is not None:
            self._content.removeWidget(self.view)
            self.view.deleteLater()
        self.view = view
        self._content.addWidget(view)
        self._content.setCurrentWidget(view)
        self._loaded = True
        self._set_dirty(False)

    # ------------------------------------------------------------------ edits

    def _on_item_changed(self, item: QStandardItem) -> None:
        self.model.blockSignals(True)  # the changes below must not re-trigger this slot
        try:
            if item.data(cm.TYPE_ROLE) == cm.BOOL:
                item.setText("true" if item.checkState() == Qt.CheckState.Checked else "false")
            cm.mark_dirty(item)
        finally:
            self.model.blockSignals(False)
        if self.view is not None:
            self.view.viewport().update()
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._update_actions()
        title = self.page_title() + (" •" if dirty else "")
        self.title_changed.emit(title)

    def _update_actions(self) -> None:
        self.save_button.setEnabled(self._loaded and self._dirty)
        self.add_button.setVisible(self.properties)
        self.add_button.setEnabled(self._loaded)

    def add_entry(self) -> None:
        index = cm.add_entry(self.model, _("new-key"))
        self._set_dirty(True)
        if self.view is not None:
            proxy_index = self.proxy.mapFromSource(index)
            self.view.scrollTo(proxy_index)
            self.view.setCurrentIndex(proxy_index)
            self.view.edit(proxy_index)

    def data(self) -> dict[str, Any]:
        return cm.model_to_data(self.model)

    def save(self, on_saved: Callable[[], None] | None = None) -> None:
        if not self._loaded or not self._dirty:
            return
        data = self.data()

        def done(_result) -> None:
            self._clear_marks()
            self._set_dirty(False)
            self.saved.emit()
            if callable(on_saved):
                on_saved()

        run_blocking(self.server.write_config, self.filename, data, success=_("Saved"),
                     disable=[self.save_button], on_success=done)

    def _clear_marks(self) -> None:
        def walk(parent: QStandardItem) -> None:
            for row in range(parent.rowCount()):
                for column in range(parent.columnCount()):
                    child = parent.child(row, column)
                    if child is not None:
                        cm.mark_dirty(child, False)
                walk(parent.child(row, 0))

        self.model.blockSignals(True)
        walk(self.model.invisibleRootItem())
        self.model.blockSignals(False)
        if self.view is not None:
            self.view.viewport().update()

    # ------------------------------------------------------------- navigation

    def can_leave(self) -> bool:
        return not self._dirty

    def confirm_leave(self, proceed: Callable[[], None]) -> None:
        dialog = MessageDialog(
            self, _("Discard changes?"),
            _("You have unsaved changes in {file}. Do you want to discard them?",
              file=self.filename),
            confirm=_("Discard"), cancel=_("Keep editing"), confirm_variant="danger",
            confirm_icon="delete",
        )

        def discard() -> None:
            self._dirty = False
            proceed()

        dialog.accepted.connect(discard)
        dialog.open()

    def dispose(self) -> None:
        pass
