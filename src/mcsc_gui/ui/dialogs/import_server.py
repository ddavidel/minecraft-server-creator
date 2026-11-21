"""Import server dialog: from an MCSC export (.zip) or from an existing server folder.

Flow: choose the source -> preview (type, version, size) -> name, RAM, EULA -> import.
The archive/folder is never changed; the server gets a new id and folder.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from mcsc import ArchiveInfo, DetectedServer, ServerType, suggested_ram_gb, total_ram_gb

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.dialogs.fields import Field, name_field, validate_name
from mcsc_gui.ui.tasks import FileProgress, run_blocking, run_task
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.backup_list import format_size
from mcsc_gui.ui.widgets.common import button, label, separator
from mcsc_gui.ui.widgets.overlay_dialog import OverlayDialog
from mcsc_gui.ui.widgets.ram_slider import RamSlider

ARCHIVE = "archive"
FOLDER = "folder"

PickPath = Callable[[QWidget], str | None]


def pick_archive(parent: QWidget) -> str | None:
    path, _filter = QFileDialog.getOpenFileName(
        parent, _("Import server"), str(Path.home()), _("MCSC export") + " (*.zip)"
    )
    return path or None


def pick_folder(parent: QWidget) -> str | None:
    path = QFileDialog.getExistingDirectory(parent, _("Import server"), str(Path.home()))
    return path or None


class ImportServerDialog(OverlayDialog):
    imported = Signal(str)  # server_id

    def __init__(self, parent: QWidget, *, choose_archive: PickPath = pick_archive,
                 choose_folder: PickPath = pick_folder) -> None:
        super().__init__(parent, _("Import server"), width=560)
        self._choose_archive = choose_archive
        self._choose_folder = choose_folder
        self.source: str | None = None  # ARCHIVE or FOLDER
        self.path: str | None = None
        self.archive_info: ArchiveInfo | None = None
        self.detected: DetectedServer | None = None
        s = TOKENS.spacing

        self.body.addWidget(label(
            _("Import a server exported from MCSC, or an existing server folder "
              "(it is copied, never moved)."), "muted", wrap=True))
        sources = QHBoxLayout()
        sources.setSpacing(s.sm)
        self.archive_button = button(_("Export file (.zip)"), "folder-zip-outline")
        self.archive_button.clicked.connect(self.choose_archive)
        self.folder_button = button(_("Server folder"), "folder")
        self.folder_button.clicked.connect(self.choose_folder)
        sources.addWidget(self.archive_button, 1)
        sources.addWidget(self.folder_button, 1)
        self.body.addLayout(sources)

        self.source_label = label("", "mono", wrap=True)
        self.source_label.hide()
        self.body.addWidget(self.source_label)
        self.error_label = label("", "error", wrap=True)
        self.error_label.hide()
        self.body.addWidget(self.error_label)

        # Details, shown once a source is loaded
        self.form = QWidget()
        form = QVBoxLayout(self.form)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(s.md)
        form.addWidget(separator())

        row = QHBoxLayout()
        row.setSpacing(s.md)
        self.type_combo = QComboBox()
        for value, text in sm.SERVER_TYPES.items():
            self.type_combo.addItem(text, value)
        self.type_field = Field(_("Server Type"), self.type_combo)
        row.addWidget(self.type_field, 1)
        self.version_edit = QLineEdit()
        self.version_edit.setPlaceholderText("1.21.4")
        self.version_field = Field(_("Server Version"), self.version_edit)
        row.addWidget(self.version_field, 1)
        form.addLayout(row)

        self.name = name_field()
        form.addWidget(self.name)
        self.ram = RamSlider(total_ram_gb(), suggested_ram_gb(), suggested_ram_gb())
        form.addWidget(self.ram)
        self.eula = QCheckBox(_("Accept EULA (Required)"))
        form.addWidget(self.eula)
        self.form.hide()
        self.body.addWidget(self.form)

        self.cancel_button = self.add_button(button(_("Cancel"), "close"))
        self.import_button = self.add_button(button(_("Import"), "import", variant="primary"))
        self.cancel_button.clicked.connect(self.reject)
        self.import_button.clicked.connect(self.submit)
        self.import_button.setDefault(True)
        self._form_widgets = [self.archive_button, self.folder_button, self.type_combo,
                              self.version_edit, self.name.widget, self.ram, self.eula,
                              self.cancel_button]
        self._update_enabled()

    # --------------------------------------------------------------- source

    def _set_error(self, message: str | None) -> None:
        self.error_label.setText(message or "")
        self.error_label.setVisible(bool(message))

    def _update_enabled(self) -> None:
        self.import_button.setEnabled(self.source is not None and not self.busy)

    def _reset(self) -> None:
        self.source = self.path = None
        self.archive_info = self.detected = None
        self.form.hide()
        self._update_enabled()

    def choose_archive(self) -> None:
        path = self._choose_archive(self)
        if path:
            self.load_archive(path)

    def choose_folder(self) -> None:
        path = self._choose_folder(self)
        if path:
            self.load_folder(path)

    def load_archive(self, path: str) -> None:
        """Read the archive manifest in the background, then show the preview."""
        self._reset()
        self._set_error(None)
        self.source_label.setText(path)
        self.source_label.show()

        def failed(error: Exception) -> None:
            self._set_error(sm.error_message(error))

        run_blocking(sm.inspect_archive, path, disable=[self.archive_button, self.folder_button],
                     on_success=lambda info: self._archive_loaded(path, info), on_error=failed,
                     show_errors=False)

    def _archive_loaded(self, path: str, info: ArchiveInfo) -> None:
        manifest = info.manifest
        self.source, self.path, self.archive_info = ARCHIVE, path, info
        self.source_label.setText(
            f"{path}\n{manifest.server_type.label} {manifest.version} · "
            f"{format_size(manifest.size_bytes)} · {manifest.file_count} " + _("files")
        )
        self.type_combo.setCurrentIndex(self.type_combo.findData(int(manifest.server_type)))
        self.version_edit.setText(manifest.version)
        for widget in (self.type_combo, self.version_edit):
            widget.setEnabled(False)  # an archive is restored as it is
        self.name.widget.setText(info.suggested_name)
        ram = manifest.server.get("ram_gb")
        if isinstance(ram, int) and ram > 0:
            self.ram.setValue(min(ram, self.ram.maximum()))
        self.eula.setChecked(info.eula_accepted)
        self.form.show()
        self._update_enabled()

    def load_folder(self, path: str) -> None:
        """Detect type and version of a server folder in the background."""
        self._reset()
        self._set_error(None)
        self.source_label.setText(path)
        self.source_label.show()

        def failed(error: Exception) -> None:
            self._set_error(sm.error_message(error))

        run_blocking(sm.detect_folder, path, disable=[self.archive_button, self.folder_button],
                     on_success=lambda detected: self._folder_loaded(path, detected),
                     on_error=failed, show_errors=False)

    def _folder_loaded(self, path: str, detected: DetectedServer) -> None:
        if detected.server_type is None:
            self._set_error(_("This folder doesn't look like a Minecraft server"))
            return
        self.source, self.path, self.detected = FOLDER, path, detected
        self.type_combo.setEnabled(True)
        self.version_edit.setEnabled(True)
        self.type_combo.setCurrentIndex(self.type_combo.findData(int(detected.server_type)))
        self.version_edit.setText(detected.version or "")
        self.name.widget.setText(sm.manager.unique_name(Path(path).name or _("Imported server")))
        self.eula.setChecked(False)
        self.form.show()
        self._update_enabled()

    # --------------------------------------------------------------- submit

    @property
    def server_type(self) -> ServerType:
        return ServerType(int(self.type_combo.currentData()))

    def submit(self) -> None:
        if self.busy or self.source is None or self.path is None:
            return
        error = validate_name(self.name.widget.text())
        self.name.set_error(error)
        version = self.version_edit.text().strip()
        version_error = _("Server version can't be empty") if not version else None
        self.version_field.set_error(version_error)
        if error or version_error:
            return

        name = self.name.widget.text().strip()
        tracker = FileProgress(_("Importing server {name}", name=name))
        if self.source == ARCHIVE:
            work = sm.import_server(self.path, name, self.ram.value(), self.eula.isChecked(),
                                    progress=tracker)
        else:
            jar = self.detected.jar if self.detected is not None \
                and self.server_type is self.detected.server_type else None
            work = sm.import_server_folder(self.path, self.server_type, version, name,
                                           self.ram.value(), self.eula.isChecked(), jar=jar)
        self.set_busy(True)
        self._update_enabled()

        def done(server) -> None:
            self.set_busy(False)
            self.imported.emit(server.id)
            self.accept()

        def failed(_error: Exception) -> None:
            self.set_busy(False)
            self._update_enabled()

        run_task(work, progress=tracker.text, success=_("Server imported!"),
                 disable=self._form_widgets, on_success=done, on_error=failed, tracker=tracker)
