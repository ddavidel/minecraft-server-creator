"""Clone server dialog: copy an existing server into a new one."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QWidget

from mcsc import MinecraftServer, suggested_ram_gb, total_ram_gb

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.dialogs.create_server import EULA_URL
from mcsc_gui.ui.dialogs.fields import Field, name_field, validate_name
from mcsc_gui.ui.tasks import run_blocking, run_task
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.common import button, label, separator
from mcsc_gui.ui.widgets.overlay_dialog import OverlayDialog
from mcsc_gui.ui.widgets.ram_slider import RamSlider


def format_size(size: int) -> str:
    """Human readable size (``"1.4 GB"``)."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"  # pragma: no cover - unreachable


class CloneServerDialog(OverlayDialog):
    """Name, RAM and EULA of the copy; type, version and the rest come from ``server``."""

    cloned = Signal(str)  # id of the new server

    def __init__(self, parent: QWidget, server: MinecraftServer, *,
                 measure: Callable[[MinecraftServer], int] = sm.server_size) -> None:
        super().__init__(parent, _("Clone server"), width=560)
        self.server = server
        config = server.config
        s = TOKENS.spacing

        intro = label(_("Creates a new server with a copy of the files of '{name}' (worlds, "
                        "plugins, mods and configuration). Its backups are not copied.",
                        name=server.name), "muted", wrap=True)
        intro.setTextFormat(Qt.TextFormat.PlainText)
        self.body.addWidget(intro)

        self.name = name_field(sm.suggest_clone_name(server))
        self.body.addWidget(self.name)

        eula_row = QHBoxLayout()
        eula_row.setSpacing(s.sm)
        self.eula = QCheckBox(_("Accept EULA (Required)"))
        self.eula.toggled.connect(self._update_enabled)
        eula_row.addWidget(self.eula)
        link = label(f'<a href="{EULA_URL}" style="color:{TOKENS.palette.accent}">'
                     f'{_("Read the EULA")}</a>', "caption")
        link.setOpenExternalLinks(True)
        eula_row.addWidget(link)
        eula_row.addStretch(1)
        self.body.addLayout(eula_row)

        self.body.addWidget(separator())
        # The source's RAM may exceed this machine's: keep it reachable
        self.ram = RamSlider(max(total_ram_gb(), config.ram_gb), config.ram_gb,
                             suggested_ram_gb())
        self.body.addWidget(self.ram)
        self.body.addWidget(separator())

        row = QHBoxLayout()
        row.setSpacing(s.md)
        for caption, value in ((_("Server Type"), config.server_type.label),
                               (_("Server Version"), config.version)):
            edit = QLineEdit(value)
            edit.setReadOnly(True)
            edit.setEnabled(False)
            row.addWidget(Field(caption, edit), 1)
        self.body.addLayout(row)

        self.size_label = label(_("Size to copy: calculating…"), "caption")
        self.body.addWidget(self.size_label)
        self.port_warning = label(
            _("The copy uses port {port}, like '{name}': don't run them at the same time.",
              port=config.port, name=server.name), "caption", wrap=True)
        self.port_warning.setTextFormat(Qt.TextFormat.PlainText)
        self.port_warning.setStyleSheet(f"color: {TOKENS.palette.warning_text};")
        self.body.addWidget(self.port_warning)

        self.cancel_button = self.add_button(button(_("Cancel"), "close"))
        self.clone_button = self.add_button(button(_("Clone"), "content_copy",
                                                   variant="primary"))
        self.cancel_button.clicked.connect(self.reject)
        self.clone_button.clicked.connect(self.submit)
        self.clone_button.setDefault(True)
        self._form_widgets = [self.name.widget, self.eula, self.ram, self.cancel_button]
        self._update_enabled()

        def measured(size: int) -> None:
            self.size_label.setText(_("Size to copy: {size}", size=format_size(size)))

        def not_measured(_error: Exception) -> None:
            self.size_label.hide()

        run_blocking(measure, server, on_success=measured, on_error=not_measured,
                     show_errors=False)

    def _update_enabled(self) -> None:
        self.clone_button.setEnabled(self.eula.isChecked() and not self.busy)

    def validate(self) -> bool:
        error = validate_name(self.name.widget.text())
        self.name.set_error(error)
        return error is None

    def submit(self) -> None:
        if self.busy or not self.eula.isChecked() or not self.validate():
            return
        name = self.name.widget.text().strip()
        self.set_busy(True)
        for widget in self._form_widgets:
            widget.setEnabled(False)
        self._update_enabled()

        def done(server: MinecraftServer) -> None:
            self.set_busy(False)
            self.cloned.emit(server.id)
            self.accept()

        def failed(_error: Exception) -> None:
            # Keep the dialog open with the entered data
            self.set_busy(False)
            for widget in self._form_widgets:
                widget.setEnabled(True)
            self._update_enabled()

        run_task(
            sm.clone_server(self.server, name=name, ram_gb=self.ram.value(),
                            accept_eula=self.eula.isChecked()),
            progress=_("Cloning server {name}", name=self.server.name),
            success=_("Server cloned!"),
            on_success=done,
            on_error=failed,
        )
