"""Update check and update dialog (US6)."""

from __future__ import annotations

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.widgets.common import button, label
from mcsc_gui.ui.widgets.overlay_dialog import OverlayDialog
from mcsc_gui.update import check_for_updates, get_latest_version

logger = logging.getLogger(__name__)


def safe_check_for_updates() -> bool:
    """``check_for_updates`` that never raises (offline, PyPI down...)."""
    try:
        return check_for_updates()
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning(f"Can't check for updates: {e}")
        return False


def safe_latest_version() -> str | None:
    """The latest version on PyPI, None if it can't be checked (never raises)."""
    try:
        return get_latest_version()
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning(f"Can't check for updates: {e}")
        return None


class UpdateAppDialog(OverlayDialog):
    """Asks to update. On confirm the window closes the app and starts the updater."""

    update_requested = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, _("Update Available"), width=460)
        self.body.addWidget(label(
            _("A new version of the app is available. Do you want to update now?"),
            "muted", wrap=True))
        self.body.addWidget(label(
            _("The app will close and the update will run in a separate window. "
              "Running servers will be stopped."),
            "caption", wrap=True))
        self.later_button = self.add_button(button(_("Later"), "close"))
        self.update_button = self.add_button(button(_("Update Now"), "download",
                                                    variant="primary"))
        self.later_button.clicked.connect(self.reject)
        self.update_button.clicked.connect(self.submit)
        self.update_button.setDefault(True)

    def submit(self) -> None:
        if self.busy:
            return
        self.accept()
        self.update_requested.emit()
