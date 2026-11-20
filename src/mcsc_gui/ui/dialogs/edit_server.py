"""Edit server dialog (US4): name, RAM and automatic backups; type, version and EULA are read-only."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QWidget

from mcsc import MinecraftServer, suggested_ram_gb, total_ram_gb

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.dialogs.fields import Field, name_field, validate_name
from mcsc_gui.ui.tasks import run_blocking
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.common import button, separator
from mcsc_gui.ui.widgets.overlay_dialog import OverlayDialog
from mcsc_gui.ui.widgets.ram_slider import RamSlider


class EditServerDialog(OverlayDialog):
    def __init__(self, parent: QWidget, server: MinecraftServer) -> None:
        super().__init__(parent, _("Edit Server"), width=560)
        self.server = server
        config = server.config

        self.name = name_field(config.name)
        self.body.addWidget(self.name)
        self.eula = QCheckBox(_("Accept EULA (Required)"))
        self.eula.setChecked(server.eula_accepted)
        self.eula.setEnabled(False)
        self.body.addWidget(self.eula)

        self.body.addWidget(separator())
        # The configured RAM may exceed this machine's: keep it reachable
        self.ram = RamSlider(max(total_ram_gb(), config.ram_gb), config.ram_gb, suggested_ram_gb())
        self.body.addWidget(self.ram)
        self.body.addWidget(separator())

        row = QHBoxLayout()
        row.setSpacing(TOKENS.spacing.md)
        type_edit = QLineEdit(config.server_type.label)
        type_edit.setReadOnly(True)
        type_edit.setEnabled(False)
        version_edit = QLineEdit(config.version)
        version_edit.setReadOnly(True)
        version_edit.setEnabled(False)
        row.addWidget(Field(_("Server Type"), type_edit), 1)
        row.addWidget(Field(_("Server Version"), version_edit), 1)
        self.body.addLayout(row)

        self.auto_backup = QComboBox()
        for policy in sm.SERVER_BACKUP_POLICIES:
            self.auto_backup.addItem(_(sm.BACKUP_POLICY_LABELS[policy]), policy)
        self._initial_policy = sm.server_backup_policy(server)
        self.auto_backup.setCurrentIndex(max(0, self.auto_backup.findData(self._initial_policy)))
        self.body.addWidget(Field(_("Automatic backups"), self.auto_backup))

        self.cancel_button = self.add_button(button(_("Cancel"), "close"))
        self.save_button = self.add_button(button(_("Save"), "save", variant="primary"))
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.submit)
        self.save_button.setDefault(True)

    def submit(self) -> None:
        if self.busy:
            return
        error = validate_name(self.name.widget.text())
        self.name.set_error(error)
        if error:
            return
        self.set_busy(True)

        def done(_result) -> None:
            self.set_busy(False)
            self.accept()

        def failed(_error: Exception) -> None:
            self.set_busy(False)

        policy = self.auto_backup.currentData()
        run_blocking(
            sm.update_server, self.server, self.name.widget.text(), self.ram.value(),
            policy if policy != self._initial_policy else None,
            progress=_("Saving settings of server '{name}'", name=self.server.name),
            success=_("Settings saved!"),
            disable=[self.save_button, self.cancel_button],
            on_success=done,
            on_error=failed,
        )
