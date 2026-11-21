"""Popup with the trend charts of a server: online players, CPU and RAM over time."""

from __future__ import annotations

import time
from collections.abc import Callable

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QVBoxLayout, QWidget

from mcsc import MinecraftServer

from mcsc_gui.core import stats_history
from mcsc_gui.core.stats_history import StatsSample
from mcsc_gui.core.translations import translate as _
from mcsc_gui.ui.tasks import run_blocking
from mcsc_gui.ui.theme.icons import icon
from mcsc_gui.ui.theme.tokens import TOKENS
from mcsc_gui.ui.widgets.common import button, label
from mcsc_gui.ui.widgets.overlay_dialog import OverlayDialog
from mcsc_gui.ui.widgets.trend_chart import TrendChart, format_value

PANEL_WIDTH = 720
HOUR = 3600
# (seconds, label) of the period selector
RANGES: tuple[tuple[int, str], ...] = (
    (HOUR, "Last hour"),
    (6 * HOUR, "Last 6 hours"),
    (24 * HOUR, "Last 24 hours"),
    (7 * 24 * HOUR, "Last 7 days"),
    (30 * 24 * HOUR, "Last 30 days"),
)
DEFAULT_RANGE = 24 * HOUR

Loader = Callable[[str, float, float], list[StatsSample]]


def _load(server_id: str, since: float, until: float) -> list[StatsSample]:
    store = stats_history.get_store()
    return [] if store is None else store.samples(server_id, since, until)


class StatsHistoryDialog(OverlayDialog):
    """Players, CPU and RAM of a server over a chosen period (from the SQLite history)."""

    def __init__(self, parent: QWidget, server: MinecraftServer, *,
                 load: Loader = _load) -> None:
        super().__init__(parent, _("Stats history · {name}", name=server.name), width=PANEL_WIDTH)
        self.server = server
        self._load = load
        p = TOKENS.palette
        s = TOKENS.spacing

        top = QHBoxLayout()
        top.setSpacing(s.sm)
        top.addWidget(label(_("Saved every minute while the server is running."), "muted",
                            wrap=True), 1)
        self.range_combo = QComboBox()
        for seconds, text in RANGES:
            self.range_combo.addItem(_(text), seconds)
        self.range_combo.setCurrentIndex(self.range_combo.findData(DEFAULT_RANGE))
        self.range_combo.setAccessibleName(_("Period"))
        self.range_combo.currentIndexChanged.connect(self.reload)
        top.addWidget(self.range_combo)
        self.body.addLayout(top)

        interval = stats_history.SAMPLE_INTERVAL
        self.players_chart = TrendChart(p.accent, interval=interval, integer=True)
        self.cpu_chart = TrendChart(p.info, "%", interval=interval)
        self.ram_chart = TrendChart(p.warning, "MB", interval=interval)
        self.peak_labels: dict[str, QWidget] = {}
        for key, icon_name, caption, chart in (
                ("players", "players", _("Online players"), self.players_chart),
                ("cpu", "memory", _("CPU usage"), self.cpu_chart),
                ("ram", "donut_large", _("RAM usage"), self.ram_chart)):
            self.body.addLayout(self._section(key, icon_name, caption, chart))

        self.close_action = self.add_button(button(_("Close"), "check", variant="primary"))
        self.close_action.clicked.connect(self.accept)
        self.reload()

    def _section(self, key: str, icon_name: str, caption: str, chart: TrendChart) -> QVBoxLayout:
        s = TOKENS.spacing
        column = QVBoxLayout()
        column.setSpacing(s.xs)
        head = QHBoxLayout()
        head.setSpacing(s.sm)
        art = label()
        art.setPixmap(icon(icon_name, chart.color).pixmap(16, 16))
        head.addWidget(art)
        head.addWidget(label(caption, "caption"), 1)
        peak = label("", "caption")
        self.peak_labels[key] = peak
        head.addWidget(peak)
        column.addLayout(head)
        chart.setMinimumHeight(120)
        chart.setAccessibleName(caption)
        column.addWidget(chart)
        return column

    @property
    def period(self) -> int:
        return int(self.range_combo.currentData() or DEFAULT_RANGE)

    def reload(self) -> None:
        until = time.time()
        since = until - self.period
        run_blocking(self._load, self.server.id, since, until,
                     on_success=lambda samples: self.set_samples(samples, since, until))

    def set_samples(self, samples: list[StatsSample], since: float, until: float) -> None:
        self.players_chart.set_points(((x.ts, x.players) for x in samples), since, until)
        self.cpu_chart.set_points(((x.ts, x.cpu_percent) for x in samples), since, until)
        self.ram_chart.set_points(((x.ts, x.ram_mb) for x in samples), since, until)
        for key, chart in (("players", self.players_chart), ("cpu", self.cpu_chart),
                           ("ram", self.ram_chart)):
            peak = chart.peak()
            self.peak_labels[key].setText(
                "" if peak is None else _("Peak: {value}", value=format_value(peak, chart.unit)))
