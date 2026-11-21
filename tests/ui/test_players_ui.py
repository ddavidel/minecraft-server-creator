"""Online players in the UI: dashboard card, server overview, settings, editor, history."""

import time
from unittest import mock

import pytest

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
from mcsc_gui.ui.widgets.trend_chart import nice_ceiling


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
    samples = [StatsSample("srv", int(now - 600), 1, 20, 10.0, 900.0),
               StatsSample("srv", int(now - 540), 3, 20, 30.0, 1200.0)]
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

    dialog.range_combo.setCurrentIndex(0)  # last hour
    qtbot.waitUntil(lambda: len(calls) == 2, timeout=2000)
    assert calls[1][1] == 3600
    dialog.grab()  # paints without errors


def test_nice_ceiling():
    assert nice_ceiling(0) == 1
    assert nice_ceiling(3) == 5
    assert nice_ceiling(12) == 20
    assert nice_ceiling(230) == 250
    assert nice_ceiling(0.4) == 1
