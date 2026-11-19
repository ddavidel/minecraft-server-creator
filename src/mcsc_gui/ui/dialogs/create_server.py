"""New server dialog (US3)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QCompleter, QHBoxLayout, QWidget

from mcsc import MinecraftServer, suggested_ram_gb, total_ram_gb

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.dialogs.fields import Field, name_field, validate_name
from mcsc_gui.ui.tasks import run_blocking, run_task
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.common import button, label, separator
from mcsc_gui.ui.widgets.overlay_dialog import OverlayDialog
from mcsc_gui.ui.widgets.ram_slider import RamSlider
from mcsc_gui.ui.widgets.spinner import Spinner

EULA_URL = "https://aka.ms/MinecraftEULA"


class CreateServerDialog(OverlayDialog):
    created = Signal(str)  # server_id

    def __init__(self, parent: QWidget,
                 load_versions: Callable[[int], list[str]] = sm.get_versions) -> None:
        super().__init__(parent, _("New Server"), width=560)
        self._load_versions = load_versions
        self._versions_request = 0
        self._loading = False
        s = TOKENS.spacing

        self.name = name_field()
        self.body.addWidget(self.name)

        eula_row = QHBoxLayout()
        eula_row.setSpacing(s.sm)
        self.eula = QCheckBox(_("Accept EULA (Required)"))
        self.eula.toggled.connect(self._update_create_enabled)
        eula_row.addWidget(self.eula)
        link = label(f'<a href="{EULA_URL}" style="color:{TOKENS.palette.accent}">'
                     f'{_("Read the EULA")}</a>', "caption")
        link.setOpenExternalLinks(True)
        eula_row.addWidget(link)
        eula_row.addStretch(1)
        self.body.addLayout(eula_row)

        self.body.addWidget(separator())
        self.ram = RamSlider(total_ram_gb(), suggested_ram_gb(), suggested_ram_gb())
        self.body.addWidget(self.ram)
        self.body.addWidget(separator())

        row = QHBoxLayout()
        row.setSpacing(s.md)
        self.type_combo = QComboBox()
        for value, text in sm.SERVER_TYPES.items():
            self.type_combo.addItem(text, value)
        self.type_field = Field(_("Server Type"), self.type_combo)
        row.addWidget(self.type_field, 1)

        version_box = QWidget()
        version_layout = QHBoxLayout(version_box)
        version_layout.setContentsMargins(0, 0, 0, 0)
        version_layout.setSpacing(s.sm)
        self.version_combo = QComboBox()
        self.version_combo.setEditable(True)
        self.version_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.version_combo.lineEdit().setPlaceholderText(_("Search version"))
        completer = QCompleter(self.version_combo.model(), self.version_combo)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.popup().setObjectName("CompleterPopup")
        self.version_combo.setCompleter(completer)
        version_layout.addWidget(self.version_combo, 1)
        self.version_spinner = Spinner(18)
        self.version_spinner.hide()
        version_layout.addWidget(self.version_spinner)
        self.version_field = Field(_("Server Version"), version_box)
        self.version_field.caption.setBuddy(self.version_combo)
        self.version_combo.setAccessibleName(_("Server Version"))
        row.addWidget(self.version_field, 1)
        self.body.addLayout(row)

        self.cancel_button = self.add_button(button(_("Cancel"), "close"))
        self.create_button = self.add_button(button(_("Create"), "add", variant="primary"))
        self.cancel_button.clicked.connect(self.reject)
        self.create_button.clicked.connect(self.submit)
        self.create_button.setDefault(True)
        self._form_widgets = [self.name.widget, self.eula, self.ram, self.type_combo,
                              self.version_combo, self.cancel_button]

        self.type_combo.currentIndexChanged.connect(self.reload_versions)
        self._update_create_enabled()
        self.reload_versions()

    # ------------------------------------------------------------- versions

    @property
    def server_type(self) -> int:
        return int(self.type_combo.currentData())

    @property
    def version(self) -> str:
        return self.version_combo.currentText().strip()

    @property
    def versions(self) -> list[str]:
        return [self.version_combo.itemText(i) for i in range(self.version_combo.count())]

    @property
    def loading(self) -> bool:
        return self._loading

    def reload_versions(self) -> None:
        """Reload the version list for the selected type (the chosen version resets)."""
        self._versions_request += 1
        request = self._versions_request
        self._set_loading(True)
        self.version_combo.clear()
        self.version_field.set_error(None)

        def loaded(versions: list[str]) -> None:
            if request != self._versions_request:
                return  # a newer request is running
            self._set_loading(False)
            self.version_combo.addItems(versions)
            self.version_combo.setCurrentIndex(0 if versions else -1)
            if not versions:
                self.version_field.set_error(_("Can't load the versions list"))

        def failed(_error: Exception) -> None:
            if request == self._versions_request:
                self._set_loading(False)
                self.version_field.set_error(_("Can't load the versions list"))

        run_blocking(self._load_versions, self.server_type, on_success=loaded,
                     on_error=failed, show_errors=False)

    def _set_loading(self, loading: bool) -> None:
        self._loading = loading
        self.version_spinner.setVisible(loading)
        self.version_combo.setEnabled(not loading and not self.busy)
        self.version_combo.lineEdit().setPlaceholderText(
            _("Loading versions…") if loading else _("Search version")
        )
        self._update_create_enabled()

    # --------------------------------------------------------------- submit

    def _update_create_enabled(self) -> None:
        self.create_button.setEnabled(self.eula.isChecked() and not self._loading and not self.busy)

    def validate(self) -> bool:
        name_error = validate_name(self.name.widget.text())
        self.name.set_error(name_error)
        version_error = None
        if not self.version:
            version_error = _("Server version can't be empty")
        elif self.versions and self.version not in self.versions:
            version_error = _("Select a version from the list")
        self.version_field.set_error(version_error)
        return name_error is None and version_error is None

    def submit(self) -> None:
        if self.busy or not self.eula.isChecked() or not self.validate():
            return
        name = self.name.widget.text().strip()
        self.set_busy(True)
        for widget in self._form_widgets:
            widget.setEnabled(False)
        self._update_create_enabled()

        def done(server: MinecraftServer) -> None:
            self.set_busy(False)
            self.created.emit(server.id)
            self.accept()

        def failed(_error: Exception) -> None:
            # Keep the dialog open with the entered data
            self.set_busy(False)
            for widget in self._form_widgets:
                widget.setEnabled(True)
            self._update_create_enabled()

        run_task(
            sm.create_server(name=name, version=self.version, server_type=self.server_type,
                             ram_gb=self.ram.value(), accept_eula=self.eula.isChecked()),
            progress=_("Creating server {name}", name=name),
            success=_("Server created!"),
            on_success=done,
            on_error=failed,
        )
