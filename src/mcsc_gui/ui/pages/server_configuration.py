"""Server configuration: the editable config files, each opening the editor."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from mcsc import MinecraftServer

from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.config_files import config_file_title, visible_config_files
from mcsc_gui.ui.navigator import CONFIGURATION
from mcsc_gui.ui.pages.server_base import ServerPage
from mcsc_gui.ui.server_events import ServerEvents
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.card import Card
from mcsc_gui.ui.widgets.common import button, label


class ConfigFileRow(Card):
    def __init__(self, filename: str, parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=TOKENS.spacing.md)
        self.filename = filename
        row = QHBoxLayout()
        row.setSpacing(TOKENS.spacing.md)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(label(config_file_title(filename), "title"))
        texts.addWidget(label(filename, "mono"))
        self.hint_label = label(
            _("Created when the server starts for the first time"), "muted")
        texts.addWidget(self.hint_label)
        row.addLayout(texts, 1)
        self.edit_button = button(_("Edit"), "edit_note", variant="primary")
        row.addWidget(self.edit_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.layout_.addLayout(row)

    def set_available(self, available: bool) -> None:
        self.edit_button.setEnabled(available)
        self.hint_label.setVisible(not available)


class ServerConfigurationPage(ServerPage):
    section = CONFIGURATION

    def __init__(self, server: MinecraftServer, events: ServerEvents,
                 parent: QWidget | None = None) -> None:
        super().__init__(server, events, parent)
        self.body.addWidget(label(
            _("The files that configure the server. Changes apply at the next start."),
            "muted", wrap=True))
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(TOKENS.spacing.md)
        self.body.addLayout(self._rows_layout)
        self.body.addStretch(1)
        self.rows: dict[str, ConfigFileRow] = {}
        self.refresh()

    def refresh(self) -> None:
        super().refresh()
        files = visible_config_files(self.server)  # they appear after the first start
        if [f for f, _e in files] != list(self.rows):
            for row in self.rows.values():
                self._rows_layout.removeWidget(row)
                row.deleteLater()
            self.rows = {}
            for filename, _enabled in files:
                row = ConfigFileRow(filename)
                row.edit_button.clicked.connect(
                    lambda _c=False, f=filename: self.edit_file_requested.emit(self.server.id, f))
                self._rows_layout.addWidget(row)
                self.rows[filename] = row
        for filename, enabled in files:
            self.rows[filename].set_available(enabled)
