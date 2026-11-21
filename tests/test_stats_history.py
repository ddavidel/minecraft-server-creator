import asyncio
import sqlite3
from pathlib import Path
from unittest import mock

import pytest

from mcsc import PaperServer, ResourceUsage, ServerConfig, ServerType

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


def test_disk_columns_round_trip(store):
    store.record(StatsSample("a", 1000, 2, 20, 10.0, 1024.0, 0.25, 1.5))
    store.record(sample(ts=1060))  # no disk data
    rows = store.samples("a", 0, 2000)
    assert (rows[0].disk_read_mb, rows[0].disk_write_mb) == (0.25, 1.5)
    assert (rows[1].disk_read_mb, rows[1].disk_write_mb) == (None, None)


def test_old_database_gets_the_disk_columns(tmp_path):
    path = tmp_path / "stats.db"
    with sqlite3.connect(path) as db:  # the schema of the first release
        db.execute("CREATE TABLE samples (server_id TEXT NOT NULL, ts INTEGER NOT NULL,"
                   " players INTEGER, max_players INTEGER, cpu_percent REAL NOT NULL,"
                   " ram_mb REAL NOT NULL)")
        db.execute("INSERT INTO samples VALUES ('a', 1000, 1, 20, 5.0, 512.0)")
    db.close()
    store = StatsStore(path)
    store.record(StatsSample("a", 1060, 2, 20, 6.0, 600.0, 0.5, 0.75))
    rows = store.samples("a", 0, 2000)
    assert rows[0] == StatsSample("a", 1000, 1, 20, 5.0, 512.0)
    assert (rows[1].disk_read_mb, rows[1].disk_write_mb) == (0.5, 0.75)


async def test_recorder_stores_the_average_disk_rate(store, tmp_path):
    server = PaperServer(ServerConfig("T", "1.21.4", ServerType.PAPER, id="s", path=tmp_path))
    server._state = server.state.RUNNING  # pylint: disable=protected-access
    readings = iter([ResourceUsage(disk_read_mb=r, disk_write_mb=w)
                     for r, w in ((0.0, 4.0), (3.0, 0.0), (0.0, 2.0), (1.0, 0.0))])

    class Monitor:
        @property
        def usage(self):
            return next(readings, ResourceUsage())

    with mock.patch.object(stats_history, "DISK_STEP", 0.01), \
            mock.patch.object(server, "monitor", Monitor()):
        recorder = StatsRecorder(server, store, interval=0.04,
                                 sample=lambda s: sample(s.id, ts=1000))
        recorder.start()
        for _wait in range(200):  # Windows timers are coarse: wait for the first row
            if store.samples("s", 0, 2000):
                break
            await asyncio.sleep(0.01)
        recorder.stop()
    row = store.samples("s", 0, 2000)[0]
    assert (row.disk_read_mb, row.disk_write_mb) == (1.0, 1.5)


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
