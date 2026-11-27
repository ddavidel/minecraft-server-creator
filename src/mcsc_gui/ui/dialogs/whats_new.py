"""
"What's New" popup: the release notes shown once after an update, and the
full changelog opened from the App Settings.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from PySide6.QtCore import QDate, QLocale, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from mcsc_gui.core.changelog import ReleaseNote, notes_between, parse_version
from mcsc_gui.core.translations import current_language
from mcsc_gui.core.translations import translate as _
from mcsc_gui.core.user_settings import UserSettings
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.common import button, label
from mcsc_gui.ui.widgets.overlay_dialog import OverlayDialog

logger = logging.getLogger(__name__)

SETTING = "last_seen_version"
RELEASES_URL = "https://github.com/ddavidel/minecraft-server-creator/releases"

PANEL_WIDTH = 560
# The notes never take more than this share of the window height (then they scroll)
MAX_HEIGHT_RATIO = 0.6


def _is_release(version: str) -> bool:
    """False for unknown / development versions (``0.0.0``)."""
    key = parse_version(version)
    return key is not None and key != (0, 0, 0)


def startup_notes(settings: UserSettings, current: str, notes: Sequence[ReleaseNote], *,
                  has_servers: bool = False) -> list[ReleaseNote]:
    """The notes to show at startup on version ``current`` (empty = show nothing).

    * fresh install (no saved setting at all, no servers): nothing;
    * upgrade from a version without this feature (settings but no
      ``last_seen_version``): the notes of ``current`` only;
    * otherwise every release in ``(last_seen_version, current]``.
    """
    if not _is_release(current):
        return []
    stored = settings.user_settings
    last = stored.get(SETTING)
    current_key = parse_version(current)
    if last is None or parse_version(str(last)) is None:
        if last is None and not has_servers and not any(key != SETTING for key in stored):
            return []  # first launch: the shortcut prompt goes first
        return [note for note in notes if note.key == current_key]
    if parse_version(str(last)) >= current_key:
        return []  # same version, or a downgrade
    return notes_between(notes, str(last), current)


def mark_seen(settings: UserSettings, current: str) -> None:
    """Remember ``current``'s notes were dealt with (never for development versions)."""
    if not _is_release(current) or settings.user_settings.get(SETTING) == current:
        return
    try:
        settings.update_settings(**{SETTING: current})
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Can't save the last seen version")


def _format_date(note: ReleaseNote, language: str) -> str:
    if note.date is None:
        return ""
    day = QDate(note.date.year, note.date.month, note.date.day)
    return QLocale(language).toString(day, "d MMMM yyyy")


class WhatsNewDialog(OverlayDialog):
    """A scrollable list of release notes, newest first."""

    def __init__(self, parent: QWidget, notes: Sequence[ReleaseNote], *,
                 title: str | None = None, close_text: str | None = None,
                 language: str | None = None) -> None:
        super().__init__(parent, title or _("What's New"), width=PANEL_WIDTH)
        self.notes = list(notes)
        self._language = language or current_language()
        s = TOKENS.spacing

        self.scroll: QScrollArea | None = None
        self.empty_label = None
        if self.notes:
            content = QWidget()
            content.setObjectName("WhatsNewContent")
            column = QVBoxLayout(content)
            column.setContentsMargins(0, 0, s.md, 0)  # room for the scroll bar
            column.setSpacing(s.lg)
            for note in self.notes:
                column.addWidget(self._release_block(note))
            column.addStretch(1)

            self.scroll = QScrollArea()
            self.scroll.setWidgetResizable(True)
            self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.scroll.setWidget(content)
            inner_width = PANEL_WIDTH - 2 * s.xl
            needed = (column.heightForWidth(inner_width) if column.hasHeightForWidth()
                      else content.sizeHint().height())
            cap = max(160, int(self._host.height() * MAX_HEIGHT_RATIO))
            self.scroll.setFixedHeight(max(80, min(needed, cap)))
            self.body.addWidget(self.scroll)
        else:
            self.empty_label = label(_("No release notes available"), "muted", wrap=True)
            self.body.addWidget(self.empty_label)

        self.releases_button = button(_("All releases on GitHub"), "open_in_new", variant="ghost")
        self.releases_button.clicked.connect(self.open_releases)
        self.buttons.insertWidget(0, self.releases_button)

        self.ok_button = self.add_button(button(close_text or _("Close"), "check",
                                                variant="primary"))
        self.ok_button.clicked.connect(self.accept)
        self.ok_button.setDefault(True)

    def _release_block(self, note: ReleaseNote) -> QWidget:
        s = TOKENS.spacing
        block = QWidget()
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(s.xs)

        header = QHBoxLayout()
        header.setSpacing(s.sm)
        header.addWidget(label(_("Version {version}", version=note.version), "title"))
        header.addStretch(1)
        when = _format_date(note, self._language)
        if when:
            header.addWidget(label(when, "caption"), 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(header)

        heading = note.heading(self._language)
        if heading:
            layout.addWidget(label(heading, "muted", wrap=True))

        for item in note.items(self._language):
            row = QHBoxLayout()
            row.setSpacing(s.sm)
            row.addWidget(label("•"), 0, Qt.AlignmentFlag.AlignTop)
            text = label(item, wrap=True)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(text, 1)
            layout.addLayout(row)
        return block

    def open_releases(self) -> None:
        QDesktopServices.openUrl(QUrl(RELEASES_URL))
