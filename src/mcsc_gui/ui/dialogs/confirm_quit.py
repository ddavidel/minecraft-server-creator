"""Quit confirmation and shutdown progress dialogs (US6)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QWidget

from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.common import label
from mcsc_gui.ui.widgets.overlay_dialog import MessageDialog, OverlayDialog
from mcsc_gui.ui.widgets.spinner import Spinner


class ConfirmQuitDialog(MessageDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(
            parent, _("Are you sure?"),
            _("There are still servers running. Are you sure you want to quit?"),
            confirm=_("Yes, quit"), cancel=_("No, take me back"), confirm_variant="danger",
        )
        self.cancel_button.setDefault(True)
        self.confirm_button.setDefault(False)


class ShutdownDialog(OverlayDialog):
    """Non-closable progress shown while the servers are being stopped."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, _("Closing"), width=420, closable=False)
        row = QHBoxLayout()
        row.setSpacing(TOKENS.spacing.md)
        row.addWidget(Spinner(22), 0, Qt.AlignmentFlag.AlignTop)
        self.message = label(_("Stopping all servers, please wait…"), "muted", wrap=True)
        row.addWidget(self.message, 1)
        self.body.addLayout(row)
        self.set_busy(True)
