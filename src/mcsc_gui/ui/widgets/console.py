"""
Server console: read-only log view + command input with history (FR-012).

* the log keeps at most ``max_lines`` lines (``QPlainTextEdit`` block limit);
* lines arrive in batches (see ``ServerEvents.output_lines``) and are appended
  in one call;
* it scrolls to the bottom only if the user was already at the bottom;
* ``[INFO]``/``WARN``/``ERROR`` levels are colored by a syntax highlighter;
* the input remembers the sent commands (Up/Down).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget

from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.common import icon_button

HISTORY_LIMIT = 100

_ERROR = re.compile(r"\b(ERROR|SEVERE|FATAL|Exception)\b|^\s+at |\bCaused by\b")
_WARN = re.compile(r"\bWARN(ING)?\b")
_INFO = re.compile(r"\bINFO\b")
_TIME = re.compile(r"^\[\d{2}:\d{2}:\d{2}[^\]]*\]")


class LogHighlighter(QSyntaxHighlighter):
    """Colors whole lines by log level and dims the timestamp."""

    def __init__(self, document) -> None:
        super().__init__(document)
        p = TOKENS.palette
        self._error = QTextCharFormat()
        self._error.setForeground(QColor(p.danger_hover))
        self._warn = QTextCharFormat()
        self._warn.setForeground(QColor(p.warning))
        self._info = QTextCharFormat()
        self._info.setForeground(QColor(p.accent))
        self._time = QTextCharFormat()
        self._time.setForeground(QColor(p.text_muted))

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt API
        if _ERROR.search(text):
            self.setFormat(0, len(text), self._error)
            return
        if _WARN.search(text):
            self.setFormat(0, len(text), self._warn)
            return
        time = _TIME.match(text)
        if time:
            self.setFormat(0, time.end(), self._time)
        info = _INFO.search(text)
        if info:
            self.setFormat(info.start(), info.end() - info.start(), self._info)


class HistoryLineEdit(QLineEdit):
    """Line edit that recalls previous entries with Up/Down."""

    submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history: list[str] = []
        self._index = 0
        self._draft = ""
        self.returnPressed.connect(self._submit)

    @property
    def history(self) -> list[str]:
        return list(self._history)

    def _submit(self) -> None:
        text = self.text().strip()
        if not text:
            return
        if not self._history or self._history[-1] != text:
            self._history.append(text)
            del self._history[:-HISTORY_LIMIT]
        self._index = len(self._history)
        self._draft = ""
        self.clear()
        self.submitted.emit(text)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        if event.key() == Qt.Key.Key_Up and self._history:
            if self._index == len(self._history):
                self._draft = self.text()
            self._index = max(0, self._index - 1)
            self.setText(self._history[self._index])
            return
        if event.key() == Qt.Key.Key_Down and self._history:
            self._index = min(len(self._history), self._index + 1)
            self.setText(self._history[self._index] if self._index < len(self._history)
                         else self._draft)
            return
        super().keyPressEvent(event)


class ConsoleView(QWidget):
    """Log + input. Emits :attr:`command_submitted` with the stripped command."""

    command_submitted = Signal(str)

    def __init__(self, max_lines: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(TOKENS.spacing.sm)

        self.log = QPlainTextEdit(self)
        self.log.setObjectName("Console")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(max_lines)
        self.log.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.log.setUndoRedoEnabled(False)
        self.log.setAccessibleName(_("Console"))
        font = QFont()
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFamilies(["IBM Plex Mono", "Cascadia Mono", "Consolas", "DejaVu Sans Mono",
                          "monospace"])
        font.setPointSizeF(9.5)
        self.log.setFont(font)
        self.highlighter = LogHighlighter(self.log.document())
        layout.addWidget(self.log, 1)

        row = QHBoxLayout()
        row.setSpacing(TOKENS.spacing.sm)
        self.input = HistoryLineEdit(self)
        self.input.setPlaceholderText(_("Write command") + "…  (↑/↓ " + _("history") + ")")
        self.input.setAccessibleName(_("Write command"))
        self.input.setFont(font)
        self.input.submitted.connect(self.command_submitted)
        row.addWidget(self.input, 1)
        self.send_button = icon_button("play_arrow", _("Send"))
        self.send_button.clicked.connect(self.input.returnPressed)
        row.addWidget(self.send_button)
        layout.addLayout(row)

    # ---------------------------------------------------------------- output

    def is_at_bottom(self) -> bool:
        bar = self.log.verticalScrollBar()
        return bar.value() >= bar.maximum() - 2

    def append_lines(self, lines: Iterable[str]) -> None:
        """Append a batch of lines, keeping the scroll position unless at the bottom."""
        lines = list(lines)
        if not lines:
            return
        bar = self.log.verticalScrollBar()
        at_bottom = self.is_at_bottom()
        position = bar.value()
        self.log.appendPlainText("\n".join(lines))
        if at_bottom:
            bar.setValue(bar.maximum())
        else:
            bar.setValue(min(position, bar.maximum()))

    def set_lines(self, lines: Iterable[str]) -> None:
        self.log.clear()
        self.append_lines(lines)
        self.scroll_to_bottom()

    def scroll_to_bottom(self) -> None:
        bar = self.log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def line_count(self) -> int:
        text = self.log.toPlainText()
        return 0 if not text else self.log.blockCount()

    def set_input_enabled(self, enabled: bool) -> None:
        self.input.setEnabled(enabled)
        self.send_button.setEnabled(enabled)
