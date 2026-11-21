"""Line chart of a stat over time (stats history popup)."""

from __future__ import annotations

import math
import time
from collections.abc import Iterable, Sequence

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QMouseEvent, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.theme.tokens import TOKENS

# A gap longer than this many sampling intervals breaks the line (server stopped)
GAP_FACTOR = 3
TICKS = 4
# The hovered sample is the nearest one within this many pixels of the cursor
HOVER_DISTANCE = 16


def nice_ceiling(value: float) -> float:
    """Smallest of 1, 2, 2.5, 5 x 10^n that is >= value (axis maximum)."""
    if value <= 0:
        return 1.0
    magnitude = 10.0 ** math.floor(math.log10(value))
    for step in (1, 2, 2.5, 5, 10):
        if round(step * magnitude, 12) >= value:
            return round(step * magnitude, 12)
    return round(10 * magnitude, 12)


def format_value(value: float, unit: str = "") -> str:
    if value >= 100 or value == int(value):
        text = f"{value:,.0f}"
    elif value >= 1:
        text = f"{value:,.1f}"
    else:  # small rates (disk MB/s) would all read 0.0
        text = f"{value:,.2f}"
    return f"{text} {unit}".strip()


def axis_labels(top: float) -> list[str]:
    """Labels of the grid lines from 0 to ``top``, with as many decimals as the step
    needs (1.25 stays 1.25 instead of rounding to 1.2)."""
    step = top / TICKS
    decimals = next((d for d in range(4) if abs(round(step, d) - step) < 1e-9), 3)
    return ["0" if i == 0 else f"{step * i:,.{decimals}f}" for i in range(TICKS + 1)]


class TrendChart(QWidget):
    """Lines of points ``(unix time, value)`` over ``[start, end]``.

    One series by default (:meth:`set_points`); with several ``colors`` and
    ``names`` the series share the axes (:meth:`set_series`) and the tooltip
    shows every value at the hovered time.
    """

    def __init__(self, color: str | Sequence[str] | None = None, unit: str = "", *,
                 names: Sequence[str] = (), interval: float = 60.0, integer: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        colors = [color] if color is None or isinstance(color, str) else list(color)
        self._colors = [QColor(c or TOKENS.palette.accent) for c in colors]
        self.names = tuple(names)
        self.unit = unit
        self.interval = interval
        self.integer = integer
        self._series: list[list[tuple[float, float]]] = [[] for _c in self._colors]
        self._times: list[float] = []  # every sample time of any series, sorted
        self._start = time.time() - 3600
        self._end = time.time()
        # Geometry of the last paint, used to map the cursor to a sample
        self._plot = QRectF()
        self._top_value = 1.0
        self._hover: int | None = None  # index in _times of the hovered sample
        self.setMouseTracking(True)
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(560, 160)

    @property
    def color(self) -> str:
        """Color of the first series."""
        return self._colors[0].name()

    @property
    def colors(self) -> list[str]:
        return [c.name() for c in self._colors]

    @property
    def points(self) -> list[tuple[float, float]]:
        """Points of the first series."""
        return list(self._series[0])

    def series(self, index: int) -> list[tuple[float, float]]:
        return list(self._series[index])

    def set_points(self, points: Iterable[tuple[float, float | None]], start: float,
                   end: float) -> None:
        self.set_series([points], start, end)

    def set_series(self, series: Sequence[Iterable[tuple[float, float | None]]], start: float,
                   end: float) -> None:
        """One iterable of points per color; ``None`` values are left out."""
        self._series = [[(float(t), float(v)) for t, v in points if v is not None]
                        for points in series]
        self._series += [[] for _c in self._colors[len(self._series):]]
        self._times = sorted({t for points in self._series for t, _v in points})
        self._start, self._end = float(start), max(float(end), float(start) + 1)
        self._hover = None
        self.update()

    def peak(self) -> float | None:
        """Highest value of every series."""
        return max((p for p in self.peaks() if p is not None), default=None)

    def peaks(self) -> list[float | None]:
        return [max((v for _t, v in points), default=None) for points in self._series]

    def values_at(self, ts: float) -> tuple[float | None, ...]:
        """Value of each series at ``ts`` (``None`` where it has no sample)."""
        return tuple(dict(points).get(ts) for points in self._series)

    @property
    def hovered(self) -> tuple[float, tuple[float | None, ...]] | None:
        """``(unix time, value of each series)`` of the sample under the cursor."""
        if self._hover is None:
            return None
        ts = self._times[self._hover]
        return ts, self.values_at(ts)

    def hover_lines(self, ts: float, values: Sequence[float | None]) -> list[str]:
        """Text of the tooltip: value(s) and when the sample was taken."""
        fmt = "%H:%M" if self._end - self._start <= 86400 else "%d/%m %H:%M"
        when = time.strftime(fmt, time.localtime(ts))
        if len(values) == 1 and not self.names:
            return [f"{format_value(values[0] or 0, self.unit)} · {when}"]
        lines = [when]
        for index, value in enumerate(values):
            name = self.names[index] if index < len(self.names) else ""
            text = "—" if value is None else format_value(value, self.unit)
            lines.append(f"{name}  {text}".strip())
        return lines

    # ---------------------------------------------------------------- hover

    def _point_at(self, ts: float, value: float) -> QPointF:
        plot, top = self._plot, self._top_value
        x = plot.left() + plot.width() * (ts - self._start) / (self._end - self._start)
        y = plot.bottom() - plot.height() * min(value, top) / top
        return QPointF(x, y)

    def _x_at(self, ts: float) -> float:
        return self._point_at(ts, 0).x()

    def sample_near(self, x: float) -> int | None:
        """Index of the sample time horizontally nearest to ``x``, if close enough."""
        if not self._times or self._plot.isEmpty():
            return None
        best = min(range(len(self._times)), key=lambda i: abs(self._x_at(self._times[i]) - x))
        if abs(self._x_at(self._times[best]) - x) > HOVER_DISTANCE:
            return None
        return best

    def _set_hover(self, index: int | None) -> None:
        if index != self._hover:
            self._hover = index
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        self._set_hover(self.sample_near(event.position().x()))
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt API
        self._set_hover(None)
        super().leaveEvent(event)

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
        labels = axis_labels(top_value)
        left = max(metrics.horizontalAdvance(t) for t in labels) + TOKENS.spacing.sm
        bottom = metrics.height() + TOKENS.spacing.xs
        plot = QRectF(left, metrics.height() / 2, self.width() - left - 2,
                      self.height() - bottom - metrics.height() / 2)
        if plot.width() <= 10 or plot.height() <= 10:
            return
        self._plot, self._top_value = plot, top_value

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

        if not self._times:
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, _("No data in this period"))
            return

        for points, color in zip(self._series, self._colors):
            self._paint_line(painter, points, color)
        hovered = self.hovered
        if hovered is not None:
            self._paint_hover(painter, metrics, *hovered)

    def _paint_line(self, painter: QPainter, points: list[tuple[float, float]],
                    color: QColor) -> None:
        if not points:
            return
        # Runs of consecutive samples; a long gap (server stopped) breaks the line
        segments: list[list[QPointF]] = []
        previous: float | None = None
        for ts, value in points:
            if previous is None or ts - previous > self.interval * GAP_FACTOR:
                segments.append([])
            segments[-1].append(self._point_at(ts, value))
            previous = ts
        line = QPainterPath()
        for segment in segments:
            line.moveTo(segment[0])
            for point in segment[1:]:
                line.lineTo(point)
        pen = QPen(color)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(line)
        # Dots for isolated samples (and for all of them when there are few)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        few = len(points) <= 90
        for segment in segments:
            if few or len(segment) == 1:
                for point in segment:
                    painter.drawEllipse(point, 2.5, 2.5)

    def _paint_hover(self, painter: QPainter, metrics: QFontMetrics, ts: float,
                     values: Sequence[float | None]) -> None:
        """Guide line, highlighted dots and a label with the hovered sample."""
        p = TOKENS.palette
        plot = self._plot
        x = self._x_at(ts)
        guide = QPen(QColor(p.border_strong))
        guide.setWidth(1)
        guide.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(guide)
        painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
        ring = QPen(QColor(p.text))
        ring.setWidth(2)
        anchor: QPointF | None = None  # the highest dot: the label goes above it
        for value, color in zip(values, self._colors):
            if value is None:
                continue
            point = self._point_at(ts, value)
            painter.setPen(ring)
            painter.setBrush(color)
            painter.drawEllipse(point, 4.5, 4.5)
            if anchor is None or point.y() < anchor.y():
                anchor = point
        if anchor is None:
            return

        lines = self.hover_lines(ts, values)
        swatches = len(lines) > 1  # a colored square before each series line
        pad = TOKENS.spacing.xs
        line_height = metrics.height()
        swatch = line_height // 2
        text_width = max(metrics.horizontalAdvance(line) for line in lines)
        box = QRectF(0, 0, text_width + 2 * pad + 2 + (swatch + pad if swatches else 0),
                     line_height * len(lines) + pad)
        # Beside the point, flipped to the left near the right edge, kept inside the plot
        gap = 8
        bx = anchor.x() + gap
        if bx + box.width() > plot.right():
            bx = anchor.x() - gap - box.width()
        by = anchor.y() - box.height() - gap
        if by < plot.top():
            by = anchor.y() + gap
        box.moveTo(max(plot.left(), bx), min(max(plot.top(), by), plot.bottom() - box.height()))
        border = QPen(QColor(p.border_strong))
        border.setWidth(TOKENS.borders.width)
        painter.setPen(border)
        painter.setBrush(QColor(p.surface_raised))
        painter.drawRect(box)
        for row, line in enumerate(lines):
            top = box.top() + pad / 2 + row * line_height
            left = box.left() + pad + 1
            if swatches:
                if row > 0:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(self._colors[row - 1])
                    painter.drawRect(QRectF(left, top + (line_height - swatch) / 2,
                                            swatch, swatch))
                left += swatch + pad
            painter.setPen(QColor(p.text_muted if swatches and row == 0 else p.text))
            painter.drawText(QRectF(left, top, box.right() - left, line_height),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)
