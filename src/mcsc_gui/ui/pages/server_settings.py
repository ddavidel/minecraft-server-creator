"""Server settings: name, RAM and automatic backups; export and delete."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLineEdit, \
    QVBoxLayout, QWidget

from mcsc import MinecraftServer, suggested_ram_gb, total_ram_gb

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui import backup_actions
from mcsc_gui.ui.dialogs.fields import Field, name_field, validate_name
from mcsc_gui.ui.navigator import SERVER_SETTINGS
from mcsc_gui.ui.pages.server_base import ServerPage
from mcsc_gui.ui.server_events import ServerEvents
from mcsc_gui.ui.tasks import run_blocking
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.card import Card
from mcsc_gui.ui.widgets.common import button, label, separator
from mcsc_gui.ui.widgets.ram_slider import RamSlider

ExportPicker = Callable[[QWidget, MinecraftServer], str | None]


class ServerSettingsPage(ServerPage):
    section = SERVER_SETTINGS

    def __init__(self, server: MinecraftServer, events: ServerEvents,
                 parent: QWidget | None = None, *,
                 choose_export_path: ExportPicker = backup_actions.pick_export_path) -> None:
        super().__init__(server, events, parent)
        self._choose_export_path = choose_export_path
        config = server.config
        s = TOKENS.spacing

        grid = QGridLayout()
        grid.setSpacing(s.lg)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)

        # --------------------------------------------------------- general
        general = Card(padding=s.lg)
        general.layout_.setSpacing(s.md)
        general.layout_.addWidget(label(_("GENERAL"), "overline"))
        self.name = name_field(config.name)
        general.layout_.addWidget(self.name)
        self.eula = QCheckBox(_("Accept EULA (Required)"))
        self.eula.setChecked(server.eula_accepted)
        self.eula.setEnabled(False)
        general.layout_.addWidget(self.eula)
        general.layout_.addWidget(separator())
        # The configured RAM may exceed this machine's: keep it reachable
        self.ram = RamSlider(max(total_ram_gb(), config.ram_gb), config.ram_gb,
                             suggested_ram_gb())
        general.layout_.addWidget(self.ram)
        general.layout_.addWidget(separator())

        row = QHBoxLayout()
        row.setSpacing(s.md)
        for caption, value in ((_("Server Type"), config.server_type.label),
                               (_("Server Version"), config.version)):
            edit = QLineEdit(value)
            edit.setReadOnly(True)
            edit.setEnabled(False)
            row.addWidget(Field(caption, edit), 1)
        general.layout_.addLayout(row)

        self.auto_backup = QComboBox()
        app_policy = _(sm.BACKUP_POLICY_LABELS[sm.app_backup_policy()])
        for policy in sm.SERVER_BACKUP_POLICIES:
            text = _(sm.BACKUP_POLICY_LABELS[policy])
            if policy == sm.DEFAULT_POLICY:
                text = f"{text} ({app_policy})"
            self.auto_backup.addItem(text, policy)
        self._saved_policy = sm.server_backup_policy(server)
        self.auto_backup.setCurrentIndex(max(0, self.auto_backup.findData(self._saved_policy)))
        general.layout_.addWidget(Field(_("Automatic backups"), self.auto_backup))

        save_row = QHBoxLayout()
        save_row.addWidget(label(_("RAM changes apply at the next start."), "muted"), 1)
        self.save_button = button(_("Save"), "save", variant="primary")
        self.save_button.clicked.connect(self.save)
        save_row.addWidget(self.save_button)
        general.layout_.addLayout(save_row)
        grid.addWidget(general, 0, 0, Qt.AlignmentFlag.AlignTop)

        # ------------------------------------------------- export / delete
        side = QVBoxLayout()
        side.setSpacing(s.lg)
        move = Card(padding=s.lg)
        move.layout_.addWidget(label(_("MOVE THE SERVER"), "overline"))
        move.layout_.addWidget(label(
            _("Export the whole server to a single .zip, to keep it or import it on "
              "another PC."), "muted", wrap=True))
        self.export_button = button(_("Export server"), "export")
        self.export_button.clicked.connect(self.export)
        move.layout_.addWidget(self.export_button, 0, Qt.AlignmentFlag.AlignLeft)
        side.addWidget(move)

        danger = Card(padding=s.lg)
        danger.setObjectName("DangerZone")
        danger.setStyleSheet(
            f"QFrame#DangerZone {{ border-color: {TOKENS.palette.danger_shadow}; }}")
        title = label(_("DANGER ZONE"), "overline")
        title.setStyleSheet(f"color: {TOKENS.palette.danger_text};")
        danger.layout_.addWidget(title)
        danger.layout_.addWidget(label(
            _("Removes the server from MCSC. You choose whether to delete its folder and "
              "its backups too."), "muted", wrap=True))
        self.delete_button = button(_("Delete server"), "delete", variant="danger")
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self.server.id))
        danger.layout_.addWidget(self.delete_button, 0, Qt.AlignmentFlag.AlignLeft)
        side.addWidget(danger)
        side.addStretch(1)
        grid.addLayout(side, 0, 1)

        self.body.addLayout(grid)
        self.body.addStretch(1)
        self.refresh()

    def refresh(self) -> None:
        super().refresh()
        busy = sm.is_busy(self.server)
        self.save_button.setEnabled(not busy)
        self.delete_button.setEnabled(not busy)
        reason = backup_actions.backup_block_reason(self.server)
        self.export_button.setEnabled(reason is None)
        self.export_button.setToolTip(reason or "")

    def save(self) -> None:
        error = validate_name(self.name.widget.text())
        self.name.set_error(error)
        if error:
            return
        policy = self.auto_backup.currentData()

        def done(_result) -> None:
            self._saved_policy = policy

        run_blocking(
            sm.update_server, self.server, self.name.widget.text(), self.ram.value(),
            policy if policy != self._saved_policy else None,
            progress=_("Saving settings of server '{name}'", name=self.server.name),
            success=_("Settings saved!"),
            disable=[self.save_button],
            on_success=done,
        )

    def export(self) -> None:
        path = self._choose_export_path(self, self.server)
        if path:
            backup_actions.export(self.server, path, [self.export_button])
