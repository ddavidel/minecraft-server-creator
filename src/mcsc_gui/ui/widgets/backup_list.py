"""Backups of a server: the full table (backups page) and the latest ones (overview)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from mcsc import Backup, BackupKind

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.card import Card
from mcsc_gui.ui.widgets.common import button, icon_button, label, separator
from mcsc_gui.ui.widgets.empty_state import EmptyState

# Column widths of the table (the date column takes the rest)
COLUMN_WIDTHS = {"kind": 170, "version": 170, "size": 110, "actions": 170}


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


def kind_color(kind: BackupKind) -> str:
    p = TOKENS.palette
    return {
        BackupKind.MANUAL: p.accent,
        BackupKind.BEFORE_RESTORE: p.warning_text,
        BackupKind.BEFORE_UPGRADE: p.warning_text,
        BackupKind.EXPORT: p.info,
    }.get(BackupKind(kind), p.text)


def kind_tag(kind: BackupKind) -> QLabel:
    """Square tag with the translated backup kind."""
    color = kind_color(kind)
    tag = label(sm.backup_kind_label(kind), "overline")
    tag.setStyleSheet(
        f"color: {color}; border: {TOKENS.borders.width}px solid {color}; padding: 1px 8px;"
    )
    tag.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return tag


def _cell(widget: QWidget, key: str) -> QWidget:
    widget.setFixedWidth(COLUMN_WIDTHS[key])
    return widget


class BackupRow(QWidget):
    restore_requested = Signal(object)  # Backup
    delete_requested = Signal(object)  # Backup

    def __init__(self, backup: Backup, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.backup = backup
        layout = QHBoxLayout(self)
        layout.setContentsMargins(TOKENS.spacing.md, TOKENS.spacing.xs, TOKENS.spacing.md,
                                  TOKENS.spacing.xs)
        layout.setSpacing(TOKENS.spacing.md)

        self.date_label = label(format_date(backup))
        self.date_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.date_label, 1)
        kind = QWidget()
        kind_layout = QHBoxLayout(kind)
        kind_layout.setContentsMargins(0, 0, 0, 0)
        self.kind_label = kind_tag(backup.kind)
        kind_layout.addWidget(self.kind_label)
        kind_layout.addStretch(1)
        layout.addWidget(_cell(kind, "kind"))
        self.version_label = _cell(label(f"{backup.server_type.label} {backup.version}", "mono"),
                                   "version")
        layout.addWidget(self.version_label)
        self.size_label = _cell(label(format_size(backup.size_bytes), "mono"), "size")
        layout.addWidget(self.size_label)

        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(TOKENS.spacing.xs)
        actions_layout.addStretch(1)
        self.restore_button = button(_("Restore"), "backup-restore")
        self.restore_button.clicked.connect(lambda: self.restore_requested.emit(self.backup))
        actions_layout.addWidget(self.restore_button)
        self.delete_button = icon_button("delete", _("Delete backup"),
                                         color=TOKENS.palette.danger)
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self.backup))
        actions_layout.addWidget(self.delete_button)
        layout.addWidget(_cell(actions, "actions"))
        self.setToolTip(backup.path.name)


class BackupTable(Card):
    """Every backup on disk, newest first, with Restore and Delete."""

    restore_requested = Signal(object)  # Backup
    delete_requested = Signal(object)  # Backup

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=0)
        self.layout_.setSpacing(0)
        self.rows: list[BackupRow] = []
        self._enabled = True
        self._delete_enabled = True
        self._reason: str | None = None

        # Column titles: hidden with the rows when there are no backups
        self.header = QWidget()
        self.header.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        header_layout = QVBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(TOKENS.spacing.md, TOKENS.spacing.md, TOKENS.spacing.md,
                                TOKENS.spacing.sm)
        head.setSpacing(TOKENS.spacing.md)
        date = label(_("DATE"), "overline")
        date.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        head.addWidget(date, 1)
        for key, text in (("kind", _("TYPE")), ("version", _("VERSION")), ("size", _("SIZE")),
                          ("actions", "")):
            head.addWidget(_cell(label(text, "overline"), key))
        header_layout.addLayout(head)
        header_layout.addWidget(separator())
        self.layout_.addWidget(self.header)

        self._rows_widget = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setContentsMargins(0, TOKENS.spacing.xs, 0, TOKENS.spacing.xs)
        self._rows_layout.setSpacing(TOKENS.spacing.xs)
        self._rows_layout.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(self._rows_widget)
        self.layout_.addWidget(self.scroll, 1)

        self.empty_state = EmptyState(
            "archive-outline", _("No backups yet"),
            _("A backup saves the whole server: world, settings and plugins. "
              "Use \"Back up now\", or turn on automatic backups."),
        )
        self.layout_.addWidget(self.empty_state, 1)

    @property
    def backups(self) -> list[Backup]:
        return [row.backup for row in self.rows]

    def set_backups(self, backups: list[Backup]) -> None:
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
        self.empty_state.setVisible(not self.rows)
        self.header.setVisible(bool(self.rows))
        self.scroll.setVisible(bool(self.rows))
        self._apply_enabled()

    def set_actions_enabled(self, enabled: bool, reason: str | None = None, *,
                            delete_enabled: bool | None = None) -> None:
        """Enable Restore (``reason`` is its tooltip when disabled) and Delete."""
        self._enabled = enabled
        self._delete_enabled = enabled if delete_enabled is None else delete_enabled
        self._reason = reason
        self._apply_enabled()

    def _apply_enabled(self) -> None:
        tooltip = self._reason if not self._enabled and self._reason else _("Restore")
        for row in self.rows:
            row.restore_button.setEnabled(self._enabled)
            row.restore_button.setToolTip(tooltip)
            row.delete_button.setEnabled(self._delete_enabled)


class RecentBackups(QWidget):
    """The latest backups as compact lines (overview)."""

    def __init__(self, limit: int = 3, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.limit = limit
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(TOKENS.spacing.xs)
        self.lines: list[QWidget] = []
        self.empty_label = label(_("No backups yet"), "muted")
        self._layout.addWidget(self.empty_label)

    def set_backups(self, backups: list[Backup]) -> None:
        for line in self.lines:
            self._layout.removeWidget(line)
            line.deleteLater()
        self.lines = []
        for backup in backups[:self.limit]:
            line = QWidget()
            row = QHBoxLayout(line)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(TOKENS.spacing.sm)
            date = label(format_date(backup))
            date.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            row.addWidget(date, 1)
            row.addWidget(label(f"{sm.backup_kind_label(backup.kind)} · "
                                f"{format_size(backup.size_bytes)}", "mono"))
            line.setToolTip(f"{backup.server_type.label} {backup.version}")
            self._layout.addWidget(line)
            self.lines.append(line)
        self.empty_label.setVisible(not self.lines)
