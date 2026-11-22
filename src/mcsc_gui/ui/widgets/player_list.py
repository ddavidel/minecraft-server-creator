"""Names of the online players of a server (server overview)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from mcsc_gui.core.players import PlayerStatus
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.theme.icons import icon
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.common import label

MAX_SHOWN = 12  # more names collapse into "and N more"


class PlayerList(QWidget):
    """One row per online player, alphabetical; a muted note when nobody is online."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._names: tuple[str, ...] = ()
        self.empty_label = label("", "muted", wrap=True)
        self._layout.addWidget(self.empty_label)
        self._rows: list[QWidget] = []
        self.note_label = label("", "caption", wrap=True)
        self.note_label.hide()
        self._layout.addWidget(self.note_label)
        self.set_status(PlayerStatus(), running=False)

    @property
    def names(self) -> tuple[str, ...]:
        return self._names

    def set_status(self, status: PlayerStatus, *, running: bool) -> None:
        names = status.names if running else ()
        if names != self._names:
            self._set_names(names)
        if not running:
            self.empty_label.setText(_("The server is not running."))
        elif not status.known:
            self.empty_label.setText(_("Can't read the online players."))
        else:
            self.empty_label.setText(_("Nobody is online."))
        self.empty_label.setVisible(not names)
        hidden = (status.online or 0) - min(len(names), MAX_SHOWN) if running else 0
        if running and names and hidden > 0:
            self.note_label.setText(_("and {count} more", count=hidden))
            self.note_label.show()
        elif running and status.partial and status.online:
            self.note_label.setText(_("Only some names are available: turn on player "
                                      "tracking in the server settings."))
            self.note_label.show()
        else:
            self.note_label.hide()

    def _set_names(self, names: tuple[str, ...]) -> None:
        for row in self._rows:
            self._layout.removeWidget(row)
            row.deleteLater()
        self._rows = []
        self._names = names
        art = icon("player", TOKENS.palette.text_muted).pixmap(16, 16)
        for index, name in enumerate(names[:MAX_SHOWN]):
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 2, 0, 2)
            line.setSpacing(TOKENS.spacing.sm)
            picture = label()
            picture.setPixmap(art)
            line.addWidget(picture)
            text = label(name)
            text.setTextFormat(Qt.TextFormat.PlainText)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            line.addWidget(text, 1)
            self._layout.insertWidget(1 + index, row)
            self._rows.append(row)
