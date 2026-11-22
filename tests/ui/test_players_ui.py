"""Online players in the UI: dashboard card, server overview, settings, editor, history."""

import time
from unittest import mock

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from mcsc import ResourceUsage, ServerState

from mcsc_gui.core import players
from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.players import PlayerStatus
from mcsc_gui.core.server_prefs import ServerPrefs
from mcsc_gui.core.stats_history import StatsSample
from mcsc_gui.ui.dialogs.stats_history import StatsHistoryDialog
from mcsc_gui.ui.pages.config_editor import ConfigEditorPage
from mcsc_gui.ui.pages.dashboard import DashboardPage
from mcsc_gui.ui.pages.server_overview import ServerOverviewPage
from mcsc_gui.ui.pages.server_settings import ServerSettingsPage
from mcsc_gui.ui.server_events import ServerEvents
from mcsc_gui.ui.usage import UsageHistory
from mcsc_gui.ui.widgets.trend_chart import TrendChart, axis_labels, format_value, nice_ceiling


@pytest.fixture
def prefs(tmp_path):
    with mock.patch.object(sm, "prefs", ServerPrefs(tmp_path / "prefs.json")) as p, \
            mock.patch.object(sm, "_settings", lambda: {}):
        yield p


@pytest.fixture
def events():
    e = ServerEvents(track_registry=False)
    yield e
    e.close()


@pytest.fixture
def server(make_server, events, prefs):
    s = make_server()
    events.attach(s)
    return s


def publish(qtbot, events, server_id, status):
    with qtbot.waitSignal(events.players_changed, timeout=1000):
        players._publish(server_id, status)  # pylint: disable=protected-access


def set_state(qtbot, events, server, state):
    with qtbot.waitSignal(events.state_changed, timeout=1000):
        server._set_state(state)  # pylint: disable=protected-access


def test_players_changed_signal(qtbot, events):
    with qtbot.waitSignal(events.players_changed, timeout=1000) as blocker:
        players._publish("srv", PlayerStatus(1, 20, ("Steve",)))  # pylint: disable=protected-access
    assert blocker.args[0] == "srv" and blocker.args[1].names == ("Steve",)


def test_card_chip_only_while_running(qtbot, server, events):
    page = DashboardPage(events, servers=lambda: [server], find=lambda _id: server)
    qtbot.addWidget(page)
    page.show()
    card = page.cards["srv"]
    assert not card.players_chip.isVisible()

    set_state(qtbot, events, server, ServerState.STARTING)
    assert not card.players_chip.isVisible()  # query not listening yet

    set_state(qtbot, events, server, ServerState.RUNNING)
    publish(qtbot, events, "srv", PlayerStatus(2, 20, ("Alex", "Steve")))
    assert card.players_chip.isVisible()
    assert card.players_label.text() == "2 / 20 players"
    assert card.players_chip.toolTip() == "Alex, Steve"

    publish(qtbot, events, "srv", PlayerStatus())
    assert card.players_label.text() == "– players"

    set_state(qtbot, events, server, ServerState.STOPPING)
    assert not card.players_chip.isVisible()  # no stale value


def test_overview_tile_and_list(qtbot, server, events):
    page = ServerOverviewPage(server, events, history=UsageHistory(), backups=lambda _s: [])
    qtbot.addWidget(page)
    page.resize(1300, 760)
    page.show()
    try:
        assert page.players_tile.value_label.text() == "—"
        assert page.player_list.empty_label.text() == "The server is not running."

        set_state(qtbot, events, server, ServerState.RUNNING)
        publish(qtbot, events, "srv", PlayerStatus(2, 20, ("Alex", "Steve")))
        assert page.players_tile.value_label.text() == "2 / 20"
        assert page.player_list.names == ("Alex", "Steve")
        assert page.player_list.empty_label.isHidden()
        assert page.players_title.text() == "PLAYERS (2 / 20)"

        server.monitor.usage = ResourceUsage(ram_mb=512, cpu_percent=5)
        page._sample_usage()  # pylint: disable=protected-access
        page._sample_usage()  # pylint: disable=protected-access
        assert page.players_tile.sparkline.values == [2.0, 2.0]

        publish(qtbot, events, "srv", PlayerStatus(0, 20))
        assert page.player_list.names == ()
        assert page.player_list.empty_label.text() == "Nobody is online."

        publish(qtbot, events, "srv", PlayerStatus(15, 20, ("Steve",), partial=True,
                                                   source="status"))
        assert page.player_list.note_label.text() == "and 14 more"

        set_state(qtbot, events, server, ServerState.STOPPED)
        assert page.players_tile.value_label.text() == "—"
        assert page.player_list.names == ()
    finally:
        page.dispose()


def test_overview_history_button_and_tiles_open_history(qtbot, server, events):
    page = ServerOverviewPage(server, events, history=UsageHistory(), backups=lambda _s: [])
    qtbot.addWidget(page)
    try:
        with mock.patch("mcsc_gui.ui.pages.server_overview.StatsHistoryDialog") as dialog:
            page.history_button.click()
            for tile in (page.players_tile, page.ram_tile, page.cpu_tile, page.read_tile,
                         page.write_tile):
                qtbot.mouseClick(tile, Qt.MouseButton.LeftButton)
        assert dialog.call_count == 6
        assert not page.ram_tile.value_label.textInteractionFlags() \
            & Qt.TextInteractionFlag.TextSelectableByMouse
    finally:
        page.dispose()


def test_settings_switch_saves_and_notes_running_change(qtbot, bridge, server, events):
    page = ServerSettingsPage(server, events)
    qtbot.addWidget(page)
    page.show()
    try:
        assert page.player_tracking.isChecked()
        assert page.tracking_note.isHidden()
        set_state(qtbot, events, server, ServerState.RUNNING)
        # The running server was started with Query on
        with mock.patch.object(players, "uses_query", lambda _id: True):
            page.player_tracking.setChecked(False)
            assert page.tracking_note.isVisible()
            with mock.patch.object(sm.manager, "save"):
                page.save()
                qtbot.waitUntil(lambda: not sm.player_tracking_enabled(server), timeout=2000)
            assert sm.prefs.get(server.id, sm.PLAYER_TRACKING_PREF) is False
            page.refresh()
            assert page.tracking_note.isVisible()  # still applies only at the next start
            page.player_tracking.setChecked(True)
            assert page.tracking_note.isHidden()
    finally:
        page.dispose()


def test_config_editor_hint_for_managed_keys(qtbot, bridge, server):
    (server.server_dir / "server.properties").write_text("enable-query=true\n",
                                                          encoding="utf-8")
    page = ConfigEditorPage(server, "server.properties")
    qtbot.addWidget(page)
    assert not page.managed_hint.isHidden()
    sm.set_player_tracking(server, False)
    other = ConfigEditorPage(server, "server.properties")
    qtbot.addWidget(other)
    assert other.managed_hint.isHidden()


def test_history_dialog_shows_the_samples(qtbot, bridge, host, server):
    now = time.time()
    samples = [StatsSample("srv", int(now - 600), 1, 20, 10.0, 900.0),  # no disk data
               StatsSample("srv", int(now - 540), 3, 20, 30.0, 1200.0, 0.5, 2.5)]
    calls = []

    def load(server_id, since, until):
        calls.append((server_id, until - since))
        return samples

    dialog = StatsHistoryDialog(host, server, load=load)
    dialog.open()
    qtbot.waitUntil(lambda: dialog.peak_labels["players"].text() != "", timeout=2000)
    assert calls[0] == ("srv", 24 * 3600)
    assert dialog.peak_labels["players"].text() == "Peak: 3"
    assert dialog.peak_labels["ram"].text() == "Peak: 1,200 MB"
    assert len(dialog.cpu_chart.points) == 2
    assert dialog.disk_chart.series(0) == [(samples[1].ts, 0.5)]
    assert dialog.peak_labels["disk"].text() == "Peak: 2.5 MB/s"

    dialog.range_combo.setCurrentIndex(0)  # last hour
    qtbot.waitUntil(lambda: len(calls) == 2, timeout=2000)
    assert calls[1][1] == 3600
    dialog.grab()  # paints without errors


def test_trend_chart_hover_shows_the_sample(qtbot):
    chart = TrendChart(unit="MB")
    qtbot.addWidget(chart)
    chart.resize(600, 160)
    now = time.time()
    chart.set_points([(now - 3000, 900.0), (now - 600, 1200.0)], now - 3600, now)
    chart.grab()  # lays out the plot

    def move_to(x: float) -> None:
        # Sent directly: the offscreen platform delivers no hover moves
        pos = QPointF(x, 80)
        QApplication.sendEvent(chart, QMouseEvent(
            QEvent.Type.MouseMove, pos, chart.mapToGlobal(pos), Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))

    x = chart._point_at(now - 600, 1200.0).x()
    move_to(x + 3)
    assert chart.hovered == (now - 600, (1200.0,))
    lines = chart.hover_lines(*chart.hovered)
    assert len(lines) == 1 and lines[0].startswith("1,200 MB · ")
    chart.grab()  # paints the tooltip without errors

    move_to(x - 150)  # far from every sample
    assert chart.hovered is None
    chart.set_points([], now - 3600, now)
    assert chart.sample_near(x) is None


def test_trend_chart_two_series_share_axes_and_tooltip(qtbot):
    chart = TrendChart(("#ff0000", "#0000ff"), "MB/s", names=("Read", "Write"))
    qtbot.addWidget(chart)
    chart.resize(600, 160)
    now = time.time()
    t1, t2 = now - 1200, now - 600
    # An older row without disk data (None) is left out of the read line only
    chart.set_series([[(t1, None), (t2, 0.5)], [(t1, 0.2), (t2, 1.5)]], now - 3600, now)
    assert chart.series(0) == [(t2, 0.5)]
    assert chart.peaks() == [0.5, 1.5] and chart.peak() == 1.5
    assert chart.values_at(t1) == (None, 0.2)
    lines = chart.hover_lines(t1, chart.values_at(t1))
    assert lines[1:] == ["Read  —", "Write  0.20 MB/s"]
    chart.grab()
    chart._set_hover(chart.sample_near(chart._x_at(t2)))  # pylint: disable=protected-access
    assert chart.hovered == (t2, (0.5, 1.5))
    chart.grab()  # paints both dots and the two-line tooltip


def test_nice_ceiling():
    assert nice_ceiling(0) == 1
    assert nice_ceiling(3) == 5
    assert nice_ceiling(12) == 20
    assert nice_ceiling(230) == 250
    assert nice_ceiling(0.4) == 0.5  # small values (disk MB/s) keep a readable axis
    assert nice_ceiling(0.03) == 0.05
    assert nice_ceiling(1) == 1


def test_format_value_keeps_small_rates_readable():
    assert format_value(1200, "MB") == "1,200 MB"
    assert format_value(2.34) == "2.3"
    assert format_value(0.042, "MB/s") == "0.04 MB/s"
    assert format_value(0) == "0"


def test_axis_labels_are_exact():
    assert axis_labels(5) == ["0", "1.25", "2.50", "3.75", "5.00"]
    assert axis_labels(4) == ["0", "1", "2", "3", "4"]
    assert axis_labels(5000) == ["0", "1,250", "2,500", "3,750", "5,000"]
    assert axis_labels(0.5) == ["0", "0.125", "0.250", "0.375", "0.500"]
