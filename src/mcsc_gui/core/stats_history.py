"""
History of the server stats (online players, CPU, RAM, disk I/O) for the trend charts.

Samples are stored in a small SQLite database (one row per running server every
:data:`SAMPLE_INTERVAL` seconds) so the same store serves the per-server charts
and, later, the Dashboard/Overview charts (aggregate CPU/RAM, players over time).
Rows older than :data:`RETENTION_DAYS` are pruned when the app starts.

While a server is running a :class:`StatsRecorder` reads ``server.monitor.usage``
and the latest :func:`mcsc_gui.core.players.status` and writes a sample. Disk I/O
comes in bursts (world saves, chunk loading), so the recorder reads it every
:data:`DISK_STEP` seconds and stores the average of the interval instead of a
single reading. No UI toolkit here: recorders run in the asyncio bridge thread.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from statistics import fmean
from pathlib import Path

from mcsc import MinecraftServer

from mcsc_gui.core import players

logger = logging.getLogger(__name__)

SAMPLE_INTERVAL = 60.0  # seconds between two samples of a running server
RETENTION_DAYS = 30
DISK_STEP = 1.0  # seconds between two disk readings (pymcsc samples every second)

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    server_id TEXT NOT NULL,
    ts INTEGER NOT NULL,          -- unix time, seconds
    players INTEGER,              -- NULL when unknown
    max_players INTEGER,
    cpu_percent REAL NOT NULL,
    ram_mb REAL NOT NULL,
    disk_read_mb REAL,            -- MB/s, average of the interval; NULL in older rows
    disk_write_mb REAL
);
CREATE INDEX IF NOT EXISTS samples_server_ts ON samples (server_id, ts);
CREATE INDEX IF NOT EXISTS samples_ts ON samples (ts);
"""
# Columns added after the first release: (name, SQL type) added to older databases
ADDED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("disk_read_mb", "REAL"),
    ("disk_write_mb", "REAL"),
)
COLUMNS = ("server_id, ts, players, max_players, cpu_percent, ram_mb, disk_read_mb,"
           " disk_write_mb")


@dataclass(frozen=True)
class StatsSample:
    server_id: str
    ts: int
    players: int | None
    max_players: int | None
    cpu_percent: float
    ram_mb: float
    disk_read_mb: float | None = None   # MB/s
    disk_write_mb: float | None = None  # MB/s


class StatsStore:
    """SQLite store of :class:`StatsSample`. Thread-safe (one connection per call)."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._ready = False

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            if not self._ready:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=5)
            try:
                if not self._ready:
                    connection.executescript(SCHEMA)
                    _add_missing_columns(connection)
                    self._ready = True
                with connection:  # commit or rollback
                    yield connection
            finally:
                connection.close()

    def record(self, sample: StatsSample) -> None:
        with self._connect() as db:
            db.execute(
                f"INSERT INTO samples ({COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (sample.server_id, int(sample.ts), sample.players, sample.max_players,
                 float(sample.cpu_percent), float(sample.ram_mb), sample.disk_read_mb,
                 sample.disk_write_mb),
            )

    def samples(self, server_id: str, since: float, until: float | None = None) -> list[StatsSample]:
        """Samples of a server in ``[since, until]``, oldest first."""
        until = time.time() if until is None else until
        with self._connect() as db:
            rows = db.execute(
                f"SELECT {COLUMNS} FROM samples WHERE server_id = ? AND ts >= ? AND ts <= ? ORDER BY ts",
                (server_id, int(since), int(until)),
            ).fetchall()
        return [StatsSample(*row) for row in rows]

    def totals(self, since: float, bucket: int, until: float | None = None,
               ) -> list[tuple[int, int | None, float, float]]:
        """All servers summed per ``bucket`` seconds: ``(bucket start, players, cpu, ram)``.

        Each server contributes its average in the bucket (for the Dashboard charts).
        """
        until = time.time() if until is None else until
        bucket = max(1, int(bucket))
        with self._connect() as db:
            rows = db.execute(
                "SELECT b, SUM(p), SUM(c), SUM(r) FROM ("
                "  SELECT (ts / ?) * ? AS b, server_id, AVG(players) AS p,"
                "         AVG(cpu_percent) AS c, AVG(ram_mb) AS r"
                "  FROM samples WHERE ts >= ? AND ts <= ? GROUP BY b, server_id"
                ") GROUP BY b ORDER BY b",
                (bucket, bucket, int(since), int(until)),
            ).fetchall()
        return [(int(b), None if p is None else round(p), float(c), float(r))
                for b, p, c, r in rows]

    def prune(self, older_than: float) -> int:
        """Delete the samples before ``older_than``. Returns how many."""
        with self._connect() as db:
            return db.execute("DELETE FROM samples WHERE ts < ?", (int(older_than),)).rowcount

    def remove_server(self, server_id: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM samples WHERE server_id = ?", (server_id,))


def _add_missing_columns(db: sqlite3.Connection) -> None:
    """Upgrade a database created by an older version (new columns are NULL)."""
    existing = {row[1] for row in db.execute("PRAGMA table_info(samples)")}
    for name, kind in ADDED_COLUMNS:
        if name not in existing:
            db.execute(f"ALTER TABLE samples ADD COLUMN {name} {kind}")


def sample_now(server: MinecraftServer, now: float | None = None) -> StatsSample:
    """Current stats of a server (resources from pymcsc, players from the tracker)."""
    usage = server.monitor.usage
    status = players.status(server.id)
    return StatsSample(server.id, int(time.time() if now is None else now), status.online,
                       status.max, usage.cpu_percent, usage.ram_mb, usage.disk_read_mb,
                       usage.disk_write_mb)


class StatsRecorder:
    """Writes a sample of one running server every ``interval`` seconds (asyncio)."""

    def __init__(self, server: MinecraftServer, store: StatsStore, *,
                 interval: float = SAMPLE_INTERVAL,
                 sample: Callable[[MinecraftServer], StatsSample] = sample_now) -> None:
        self.server = server
        self.store = store
        self.interval = interval
        self._sample = sample
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if not self.running:
            self._task = asyncio.ensure_future(self._run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        # The first sample after one interval: the CPU/players of a just started
        # server are not meaningful yet.
        ticks = max(1, round(self.interval / DISK_STEP))
        step = self.interval / ticks
        while True:
            reads: list[float] = []
            writes: list[float] = []
            for _tick in range(ticks):
                await asyncio.sleep(step)
                if self.server.is_active:
                    usage = self.server.monitor.usage
                    reads.append(usage.disk_read_mb)
                    writes.append(usage.disk_write_mb)
            if not self.server.is_active:
                continue
            sample = self._sample(self.server)
            if reads:  # the average of the interval, not the last second only
                sample = replace(sample, disk_read_mb=round(fmean(reads), 3),
                                 disk_write_mb=round(fmean(writes), 3))
            try:
                await asyncio.to_thread(self.store.record, sample)
            except (OSError, sqlite3.Error) as e:
                logger.warning(f"Can't save the stats of server {self.server.id}: {e}")


_recorders: dict[str, StatsRecorder] = {}
_store: StatsStore | None = None


def configure(store: StatsStore | None) -> None:
    """Set the store used by :func:`start_recording` (``None`` turns recording off)."""
    global _store  # pylint: disable=global-statement
    _store = store


def get_store() -> StatsStore | None:
    return _store


def start_recording(server: MinecraftServer, **options) -> StatsRecorder | None:
    """Start sampling a running server (call from the asyncio loop)."""
    if _store is None:
        return None
    recorder = _recorders.get(server.id)
    if recorder is None:
        recorder = _recorders[server.id] = StatsRecorder(server, _store, **options)
    recorder.start()
    return recorder


def stop_recording(server_id: str) -> None:
    recorder = _recorders.pop(server_id, None)
    if recorder is not None:
        recorder.stop()


def prune_old(now: float | None = None) -> None:
    """Delete samples older than :data:`RETENTION_DAYS`. Blocking, never raises."""
    if _store is None:
        return
    now = time.time() if now is None else now
    try:
        removed = _store.prune(now - RETENTION_DAYS * 86400)
    except (OSError, sqlite3.Error) as e:
        logger.warning(f"Can't prune the stats history: {e}")
        return
    if removed:
        logger.info(f"Removed {removed} old stats samples")
