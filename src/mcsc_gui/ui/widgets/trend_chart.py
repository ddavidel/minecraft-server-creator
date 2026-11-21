"""Line chart of a stat over time (stats history popup)."""

from __future__ import annotations

import math
import time
from collections.abc import Iterable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.theme.tokens import TOKENS

# A gap longer than this many sampling intervals breaks the line (server stopped)
GAP_FACTOR = 3
TICKS = 4


def nice_ceiling(value: float) -> float:
    """Smallest of 1, 2, 2.5, 5 x 10^n that is >= value (axis maximum)."""
    if value <= 0:
        return 1.0
    magnitude = 10 ** (len(str(int(value))) - 1) if value >= 1 else 1
    for step in (1, 2, 2.5, 5, 10):
        if step * magnitude >= value:
            return float(step * magnitude)
    return float(10 * magnitude)


def format_value(value: float, unit: str = "") -> str:
    text = f"{value:,.0f}" if value >= 100 or value == int(value) else f"{value:,.1f}"
    return f"{text} {unit}".strip()


class TrendChart(QWidget):
    """Points ``(unix time, value)`` drawn as a line over ``[start, end]``."""

    def __init__(self, color: str | None = None, unit: str = "", *,
                 interval: float = 60.0, integer: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor(color or TOKENS.palette.accent)
        self.unit = unit
        self.interval = interval
        self.integer = integer
        self._points: list[tuple[float, float]] = []
        self._start = time.time() - 3600
        self._end = time.time()
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(560, 160)

    @property
    def color(self) -> str:
        return self._color.name()

    @property
    def points(self) -> list[tuple[float, float]]:
        return list(self._points)

    def set_points(self, points: Iterable[tuple[float, float | None]], start: float,
                   end: float) -> None:
        self._points = [(float(t), float(v)) for t, v in points if v is not None]
        self._start, self._end = float(start), max(float(end), float(start) + 1)
        self.update()

    def peak(self) -> float | None:
        return max((v for _t, v in self._points), default=None)

    # ------------------------------------------------------------- painting

    def _time_label(self, ts: float) -> str:
        fmt = "%H:%M" if self._end - self._start <= 86400 else "%d/%m"
        return time.strftime(fmt, time.localtime(ts))

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        p = TOKENS.palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(self.font())
        font.setPixelSize(TOKENS.typography.caption)
        painter.setFont(font)
        metrics = QFontMetrics(font)

        if self.integer:  # whole numbers on every grid line
            top_value = float(TICKS * max(1, math.ceil((self.peak() or 0) / TICKS)))
        else:
            top_value = nice_ceiling(self.peak() or 1.0)
        labels = [format_value(top_value * i / TICKS) for i in range(TICKS + 1)]
        left = max(metrics.horizontalAdvance(t) for t in labels) + TOKENS.spacing.sm
        bottom = metrics.height() + TOKENS.spacing.xs
        plot = QRectF(left, metrics.height() / 2, self.width() - left - 2,
                      self.height() - bottom - metrics.height() / 2)
        if plot.width() <= 10 or plot.height() <= 10:
            return

        # Grid and value labels
        grid = QPen(QColor(p.border))
        grid.setWidth(1)
        for i, text in enumerate(labels):
            y = plot.bottom() - plot.height() * i / TICKS
            painter.setPen(grid)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(p.text_muted))
            painter.drawText(QRectF(0, y - metrics.height() / 2, left - TOKENS.spacing.xs,
                                    metrics.height()),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)

        # Time labels
        span = self._end - self._start
        painter.setPen(QColor(p.text_muted))
        for i in range(TICKS + 1):
            ts = self._start + span * i / TICKS
            x = plot.left() + plot.width() * i / TICKS
            text = self._time_label(ts)
            width = metrics.horizontalAdvance(text)
            x = min(max(x - width / 2, plot.left()), plot.right() - width)
            painter.drawText(QPointF(x, self.height() - TOKENS.spacing.xs / 2), text)

        if not self._points:
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, _("No data in this period"))
            return

        def at(ts: float, value: float) -> QPointF:
            x = plot.left() + plot.width() * (ts - self._start) / span
            y = plot.bottom() - plot.height() * min(value, top_value) / top_value
            return QPointF(x, y)

        # Runs of consecutive samples; a long gap (server stopped) breaks the line
        segments: list[list[QPointF]] = []
        previous: float | None = None
        for ts, value in self._points:
            if previous is None or ts - previous > self.interval * GAP_FACTOR:
                segments.append([])
            segments[-1].append(at(ts, value))
            previous = ts
        line = QPainterPath()
        for segment in segments:
            line.moveTo(segment[0])
            for point in segment[1:]:
                line.lineTo(point)
        pen = QPen(self._color)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawPath(line)
        # Dots for isolated samples (and for all of them when there are few)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        few = len(self._points) <= 90
        for segment in segments:
            if few or len(segment) == 1:
                for point in segment:
                    painter.drawEllipse(point, 2.5, 2.5)
