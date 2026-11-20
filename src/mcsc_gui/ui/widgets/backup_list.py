"""Backups of a server: "Back up now", "Open backups folder" and one row per backup."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from mcsc import Backup

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.card import Card
from mcsc_gui.ui.widgets.common import button, icon_button, label

LIST_MAX_HEIGHT = 220


def format_size(size: int) -> str:
    """Human readable size: ``"12.3 MB"``."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"  # pragma: no cover - unreachable


def format_date(backup: Backup) -> str:
    """Local date and time of a backup."""
    return backup.created_at.astimezone().strftime("%Y-%m-%d %H:%M")


class BackupRow(QWidget):
    restore_requested = Signal(object)  # Backup
    delete_requested = Signal(object)  # Backup

    def __init__(self, backup: Backup, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.backup = backup
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(TOKENS.spacing.xs)

        texts = QVBoxLayout()
        texts.setSpacing(0)
        top = QHBoxLayout()
        top.setSpacing(TOKENS.spacing.xs)
        self.title_label = label(format_date(backup))
        self.size_label = label(format_size(backup.size_bytes), "mono")
        self.size_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.details_label = label(
            f"{sm.backup_kind_label(backup.kind)} · {backup.version}", "mono")
        for text in (self.title_label, self.details_label):
            # Long texts are clipped instead of pushing the buttons out of the row
            text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        top.addWidget(self.title_label, 1)
        top.addWidget(self.size_label)
        texts.addLayout(top)
        texts.addWidget(self.details_label)
        layout.addLayout(texts, 1)

        self.restore_button = icon_button("backup-restore", _("Restore"))
        self.restore_button.clicked.connect(lambda: self.restore_requested.emit(self.backup))
        layout.addWidget(self.restore_button)
        self.delete_button = icon_button("delete", _("Delete backup"),
                                         color=TOKENS.palette.danger)
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self.backup))
        layout.addWidget(self.delete_button)
        self.setToolTip(f"{sm.backup_kind_label(backup.kind)} · {backup.server_type.label} "
                        f"{backup.version} · {format_size(backup.size_bytes)}\n{backup.path.name}")


class BackupList(QWidget):
    """Lists what is on disk; call :meth:`reload` when the backups change."""

    backup_requested = Signal()
    open_folder_requested = Signal()
    restore_requested = Signal(object)  # Backup
    delete_requested = Signal(object)  # Backup

    def __init__(self, load: Callable[[], list[Backup]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._load = load
        self._enabled = True
        self._delete_enabled = True
        self._restore_tooltip: str | None = None
        self.rows: list[BackupRow] = []
        s = TOKENS.spacing

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(s.sm)

        header = QHBoxLayout()
        header.setSpacing(s.xs)
        header.addWidget(label(_("BACKUPS"), "overline"), 1)
        self.folder_button = icon_button("folder", _("Open backups folder"))
        self.folder_button.clicked.connect(self.open_folder_requested)
        header.addWidget(self.folder_button)
        root.addLayout(header)

        card = Card(padding=s.sm)
        card.layout_.setSpacing(s.sm)
        self.backup_button = button(_("Back up now"), "archive-arrow-down-outline",
                                    variant="primary")
        self.backup_button.clicked.connect(self.backup_requested)
        card.layout_.addWidget(self.backup_button)

        self.empty_label = label(_("No backups yet"), "muted")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card.layout_.addWidget(self.empty_label)

        self._rows_widget = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(s.sm)
        self._rows_layout.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(self._rows_widget)
        self.scroll.setMaximumHeight(LIST_MAX_HEIGHT)
        card.layout_.addWidget(self.scroll)
        root.addWidget(card)

        self.reload()

    @property
    def backups(self) -> list[Backup]:
        return [row.backup for row in self.rows]

    def reload(self) -> None:
        """Re-read the backups from disk."""
        try:
            backups = self._load()
        except OSError:
            backups = []
        for row in self.rows:
            self._rows_layout.removeWidget(row)
            row.deleteLater()
        self.rows = []
        for index, backup in enumerate(backups):
            row = BackupRow(backup)
            row.restore_requested.connect(self.restore_requested)
            row.delete_requested.connect(self.delete_requested)
            self._rows_layout.insertWidget(index, row)
            self.rows.append(row)
        self.empty_label.setVisible(not self.rows)
        self.scroll.setVisible(bool(self.rows))
        # Height of the rows, capped: the list scrolls beyond LIST_MAX_HEIGHT
        self.scroll.setMinimumHeight(min(LIST_MAX_HEIGHT, self._rows_widget.sizeHint().height()))
        self._apply_enabled()

    def set_actions_enabled(self, enabled: bool, reason: str | None = None, *,
                            delete_enabled: bool | None = None) -> None:
        """Enable "Back up now" and restore (``reason`` is their tooltip when disabled)
        and the delete buttons (``delete_enabled``, default ``enabled``)."""
        self._enabled = enabled
        self._delete_enabled = enabled if delete_enabled is None else delete_enabled
        self._restore_tooltip = reason
        self._apply_enabled()

    def _apply_enabled(self) -> None:
        enabled = self._enabled
        reason = None if enabled else self._restore_tooltip
        self.backup_button.setEnabled(enabled)
        self.backup_button.setToolTip(reason or "")
        for row in self.rows:
            row.restore_button.setEnabled(enabled)
            row.restore_button.setToolTip(reason or _("Restore"))
            row.delete_button.setEnabled(self._delete_enabled)
