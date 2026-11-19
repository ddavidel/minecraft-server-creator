"""Delete server dialog (US4): confirm by typing the name."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QLineEdit, QWidget

from mcsc import MinecraftServer

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.dialogs.fields import Field
from mcsc_gui.ui.tasks import run_task
from mcsc_gui.ui.widgets.common import button, label
from mcsc_gui.ui.widgets.overlay_dialog import OverlayDialog


class DeleteServerDialog(OverlayDialog):
    deleted = Signal(str)  # server_id

    def __init__(self, parent: QWidget, server: MinecraftServer) -> None:
        super().__init__(parent, _("Are you sure?"), width=480)
        self.server = server

        self.body.addWidget(label(_("Write '{name}' below to confirm", name=server.name),
                                  "muted", wrap=True))
        self.confirm_edit = QLineEdit()
        self.confirm_edit.setPlaceholderText(server.name)
        self.confirm_field = Field(_("Confirm name"), self.confirm_edit)
        self.body.addWidget(self.confirm_field)
        self.delete_files = QCheckBox(_("Delete server folder"))
        self.body.addWidget(self.delete_files)

        self.cancel_button = self.add_button(button(_("Cancel"), "close"))
        self.delete_button = self.add_button(button(_("Delete"), "delete", variant="danger"))
        self.cancel_button.clicked.connect(self.reject)
        self.delete_button.clicked.connect(self.submit)
        self.confirm_edit.textChanged.connect(self._update_enabled)
        self.confirm_edit.returnPressed.connect(self.submit)
        self._update_enabled()

    def _matches(self) -> bool:
        return self.confirm_edit.text() == self.server.name

    def _update_enabled(self) -> None:
        self.delete_button.setEnabled(self._matches() and not self.busy)
        typed = self.confirm_edit.text()
        self.confirm_field.set_error(_("Wrong name") if typed and not self._matches() else None)

    def submit(self) -> None:
        if self.busy or not self._matches():
            return
        self.set_busy(True)
        self._update_enabled()

        def done(_result) -> None:
            self.set_busy(False)
            self.deleted.emit(self.server.id)
            self.accept()

        def failed(_error: Exception) -> None:
            self.set_busy(False)
            self._update_enabled()

        run_task(
            sm.delete_server(self.server, delete_files=self.delete_files.isChecked()),
            progress=_("Deleting server {name}", name=self.server.name),
            success=_("Server deleted"),
            disable=[self.cancel_button, self.confirm_edit, self.delete_files],
            on_success=done,
            on_error=failed,
        )
