import asyncio
from pathlib import Path

import pytest

from mcsc import PaperServer, ServerConfig, ServerType

from mcsc_gui.core import players, stats_history
from mcsc_gui.core.stats_history import StatsRecorder, StatsSample, StatsStore


@pytest.fixture
def store(tmp_path: Path):
    return StatsStore(tmp_path / "data" / "stats.db")


def sample(server_id="a", ts=1000, players_=2, cpu=10.0, ram=1024.0):
    return StatsSample(server_id, ts, players_, 20, cpu, ram)


def test_record_and_read_back(store):
    store.record(sample(ts=1000))
    store.record(sample(ts=1060, players_=None))
    store.record(sample("b", ts=1030))
    rows = store.samples("a", 0, 2000)
    assert [r.ts for r in rows] == [1000, 1060]
    assert rows[1].players is None
    assert store.samples("a", 1050, 2000) == [rows[1]]


def test_totals_sum_the_servers_per_bucket(store):
    store.record(sample("a", ts=1000, players_=2, cpu=10, ram=1000))
    store.record(sample("a", ts=1010, players_=4, cpu=20, ram=2000))
    store.record(sample("b", ts=1015, players_=1, cpu=5, ram=500))
    store.record(sample("b", ts=1200, players_=3, cpu=5, ram=500))
    totals = store.totals(0, 60, until=2000)
    # bucket 960: a averages 3 players / 15% / 1500 MB, plus b
    assert totals[0] == (960, 4, 20.0, 2000.0)
    assert totals[1] == (1200, 3, 5.0, 500.0)


def test_prune_and_remove_server(store):
    store.record(sample(ts=100))
    store.record(sample(ts=5000))
    store.record(sample("b", ts=5000))
    assert store.prune(1000) == 1
    store.remove_server("a")
    assert store.samples("a", 0, 10000) == []
    assert len(store.samples("b", 0, 10000)) == 1


def test_sample_now_reads_usage_and_players(tmp_path):
    server = PaperServer(ServerConfig("T", "1.21.4", ServerType.PAPER, id="s", path=tmp_path))
    players._publish("s", players.PlayerStatus(3, 10))  # pylint: disable=protected-access
    try:
        row = stats_history.sample_now(server, now=1234)
    finally:
        players.stop_tracking("s")
    assert (row.server_id, row.ts, row.players, row.max_players) == ("s", 1234, 3, 10)


async def test_recorder_writes_while_active(store, tmp_path):
    server = PaperServer(ServerConfig("T", "1.21.4", ServerType.PAPER, id="s", path=tmp_path))
    server._state = server.state.RUNNING  # pylint: disable=protected-access
    recorder = StatsRecorder(server, store, interval=0.02,
                             sample=lambda s: sample(s.id, ts=1000))
    recorder.start()
    await asyncio.sleep(0.1)
    recorder.stop()
    assert len(store.samples("s", 0, 2000)) >= 1


def test_prune_old_uses_retention(store):
    previous = stats_history.get_store()
    stats_history.configure(store)
    try:
        now = 100 * 86400
        store.record(sample(ts=now - (stats_history.RETENTION_DAYS + 1) * 86400))
        store.record(sample(ts=now - 86400))
        stats_history.prune_old(now)
        assert len(store.samples("a", 0, now)) == 1
    finally:
        stats_history.configure(previous)
