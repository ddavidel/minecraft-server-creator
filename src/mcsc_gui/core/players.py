"""
Online players of the running servers.

pymcsc knows nothing about players: the app asks each running server through the
Minecraft **Query** protocol (UDP, GameSpy4) with ``mcstatus``. Query gives the
online count, the max players and the full list of names. If it doesn't answer
(turned off, port blocked) the app falls back to the **Server List Ping** (TCP,
always on), which only gives the count and a sample of up to 12 names.

Query has to be turned on in ``server.properties``: :func:`ensure_query_enabled`
does it before every start (see :mod:`mcsc_gui.core.server_manager`) unless the
user turned player tracking off for the server.

One :class:`PlayerTracker` polls each running server every :data:`POLL_INTERVAL`
seconds; a console line about a player joining or leaving triggers an extra
poll (:func:`poke`). Statuses are published to the listeners registered with
:func:`add_listener` and can be read at any time with :func:`status`.

No UI toolkit here: the trackers run in the asyncio bridge thread and listeners
are called there.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from mcsc import MinecraftServer

from mcsc_gui.core import ansi

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5.0  # seconds between two polls of a running server
QUERY_TIMEOUT = 1.0  # seconds before a query (or a status ping) gives up
POKE_DEBOUNCE = 0.5  # seconds: a burst of join/leave lines gives one extra poll

DEFAULT_PORT = 25565
LOCAL_HOST = "127.0.0.1"
# server.properties keys the app manages while tracking is on
QUERY_KEYS = ("enable-query", "query.port")

# "Steve joined the game" / "Steve left the game" (vanilla, Paper, Forge)
JOIN_LEAVE_PATTERN = re.compile(r"\]: (?:\S+) (?:joined|left) the game\s*$")

Source = Literal["query", "status", "none"]


@dataclass(frozen=True)
class PlayerStatus:
    """Players of a server at ``updated_at`` (``online is None``: unknown)."""

    online: int | None = None
    max: int | None = None
    names: tuple[str, ...] = ()
    partial: bool = False  # True when the names come from the Server List Ping sample
    source: Source = "none"
    updated_at: float = field(default_factory=time.time)

    @property
    def known(self) -> bool:
        return self.online is not None

    def label(self) -> str:
        """``"3 / 20"``, or ``"–"`` when the count is unknown."""
        if self.online is None:
            return "–"
        if self.max is None:
            return str(self.online)
        return f"{self.online} / {self.max}"


NO_PLAYERS = PlayerStatus()


def _sorted_names(names: Any) -> tuple[str, ...]:
    return tuple(sorted({str(n) for n in names or () if str(n).strip()}, key=str.casefold))


# --------------------------------------------------------- server.properties


def _port(value: Any, default: int = DEFAULT_PORT) -> int:
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return port if 0 < port < 65536 else default


def server_port(properties: dict[str, str]) -> int:
    """The game port in ``server.properties`` (25565 when missing)."""
    return _port(properties.get("server-port", DEFAULT_PORT))


def ensure_query_enabled(server: MinecraftServer) -> bool:
    """Set ``enable-query=true`` and ``query.port=<server-port>``. Blocking.

    A server that never started has no ``server.properties`` yet: a minimal
    one with these two keys is written and Minecraft fills in the rest. Every
    other key is left as it is. Returns True if the file changed.
    """
    properties = dict(server.read_properties())
    port = server_port(properties) if properties else _port(server.config.port)
    wanted = {"enable-query": "true", "query.port": str(port)}
    if all(properties.get(k, "").strip().lower() == v for k, v in wanted.items()):
        return False
    created = not properties
    properties.update(wanted)
    server.server_dir.mkdir(parents=True, exist_ok=True)
    server.write_properties(properties)
    logger.info(f"{'Created' if created else 'Updated'} server.properties of server "
                f"{server.id}: enable-query=true, query.port={port}")
    return True


def query_target(server: MinecraftServer) -> tuple[str, int, int]:
    """``(host, query port, game port)`` to poll a local server. Blocking."""
    try:
        properties = server.read_properties()
    except (OSError, ValueError) as e:
        logger.warning(f"Can't read server.properties of server {server.id}: {e}")
        properties = {}
    game_port = server_port(properties) if properties else _port(server.config.port)
    query_port = _port(properties.get("query.port"), game_port)
    host = (properties.get("server-ip") or "").strip() or server.config.address or ""
    if not host or host in ("0.0.0.0", "::", "default"):
        host = LOCAL_HOST
    return host, query_port, game_port


# --------------------------------------------------------------- polling


async def _mcstatus_query(host: str, port: int, timeout: float) -> PlayerStatus:
    from mcstatus import JavaServer  # pylint: disable=import-outside-toplevel

    response = await JavaServer(host, port, timeout=timeout).async_query()
    players = response.players
    return PlayerStatus(players.online, players.max, _sorted_names(players.names),
                        partial=False, source="query")


async def _mcstatus_status(host: str, port: int, timeout: float) -> PlayerStatus:
    from mcstatus import JavaServer  # pylint: disable=import-outside-toplevel

    response = await JavaServer(host, port, timeout=timeout).async_status()
    players = response.players
    names = _sorted_names(p.name for p in (players.sample or ()))
    return PlayerStatus(players.online, players.max, names, partial=True, source="status")


Fetcher = Callable[[str, int, float], Awaitable[PlayerStatus]]


class PlayerTracker:
    """Polls one running server. Lives in the asyncio loop it was started in."""

    def __init__(self, server: MinecraftServer, publish: Callable[[str, PlayerStatus], None],
                 *, use_query: bool = True, interval: float = POLL_INTERVAL,
                 timeout: float = QUERY_TIMEOUT, debounce: float = POKE_DEBOUNCE,
                 query: Fetcher = _mcstatus_query, ping: Fetcher = _mcstatus_status) -> None:
        self.server = server
        self.use_query = use_query
        self.interval = interval
        self.timeout = timeout
        self.debounce = debounce
        self._publish = publish
        self._query = query
        self._ping = ping
        self._task: asyncio.Task | None = None
        self._poke: asyncio.TimerHandle | None = None
        self._wake: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._warned = False
        self._target: tuple[str, int, int] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Start polling (call from the loop's thread)."""
        if self.running:
            return
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        self._task = asyncio.ensure_future(self._run())

    def stop(self) -> None:
        """Stop polling (call from the loop's thread)."""
        if self._poke is not None:
            self._poke.cancel()
            self._poke = None
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def poke(self) -> None:
        """Poll again soon (debounced). Call from the loop's thread."""
        if not self.running or self._loop is None or self._poke is not None:
            return

        def fire() -> None:
            self._poke = None
            if self._wake is not None:
                self._wake.set()

        self._poke = self._loop.call_later(self.debounce, fire)

    async def poll(self) -> PlayerStatus:
        """Ask the server once: Query, then the Server List Ping."""
        if self._target is None:
            self._target = await asyncio.to_thread(query_target, self.server)
        host, query_port, game_port = self._target
        errors = []
        if self.use_query:
            try:
                return await asyncio.wait_for(self._query(host, query_port, self.timeout),
                                              self.timeout * 4)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # pylint: disable=broad-exception-caught
                errors.append(f"query: {e!r}")
        try:
            return await asyncio.wait_for(self._ping(host, game_port, self.timeout),
                                          self.timeout * 4)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # pylint: disable=broad-exception-caught
            errors.append(f"status: {e!r}")
        if not self._warned:
            self._warned = True
            logger.warning(f"Can't read the players of server {self.server.id} "
                           f"({host}): {'; '.join(errors)}")
        return PlayerStatus()

    async def _run(self) -> None:
        assert self._wake is not None
        while True:
            status = await self.poll()
            if status.known:
                self._warned = False
            self._publish(self.server.id, status)
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), self.interval)
            except asyncio.TimeoutError:
                pass


# ------------------------------------------------------------- registry

_lock = threading.Lock()
_statuses: dict[str, PlayerStatus] = {}
_trackers: dict[str, PlayerTracker] = {}
Listener = Callable[[str, PlayerStatus], Any]
_listeners: list[Listener] = []


def add_listener(listener: Listener) -> None:
    """Call ``listener(server_id, status)`` on every new status (in the bridge thread)."""
    with _lock:
        _listeners.append(listener)


def remove_listener(listener: Listener) -> None:
    with _lock:
        while listener in _listeners:
            _listeners.remove(listener)


def _publish(server_id: str, status: PlayerStatus) -> None:
    with _lock:
        previous = _statuses.get(server_id, NO_PLAYERS)
        _statuses[server_id] = status
        listeners = list(_listeners)
    if (previous.online, previous.max, previous.names, previous.source) == \
            (status.online, status.max, status.names, status.source):
        return
    for listener in listeners:
        try:
            listener(server_id, status)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception(f"Players listener {listener!r} failed")


def status(server_id: str) -> PlayerStatus:
    """Latest players of a server (:data:`NO_PLAYERS` if it isn't tracked)."""
    with _lock:
        return _statuses.get(server_id, NO_PLAYERS)


def names(server_id: str) -> tuple[str, ...]:
    """Names of the online players, sorted (used by the console command suggestions)."""
    return status(server_id).names


def is_tracking(server_id: str) -> bool:
    with _lock:
        return server_id in _trackers


def uses_query(server_id: str) -> bool | None:
    """Whether the server's tracker uses Query (``None`` if it isn't tracked)."""
    with _lock:
        tracker = _trackers.get(server_id)
    return None if tracker is None else tracker.use_query


def start_tracking(server: MinecraftServer, *, use_query: bool = True,
                   **options: Any) -> PlayerTracker:
    """Start polling a running server (call from the asyncio loop)."""
    with _lock:
        tracker = _trackers.get(server.id)
        if tracker is None:
            tracker = PlayerTracker(server, _publish, use_query=use_query, **options)
            _trackers[server.id] = tracker
    tracker.start()
    return tracker


def stop_tracking(server_id: str) -> None:
    """Stop polling a server and publish "no players" (call from the asyncio loop)."""
    with _lock:
        tracker = _trackers.pop(server_id, None)
    if tracker is not None:
        tracker.stop()
    _publish(server_id, PlayerStatus())
    with _lock:
        _statuses.pop(server_id, None)


def poke(server_id: str) -> None:
    """A player joined or left: poll the server again soon (asyncio loop)."""
    with _lock:
        tracker = _trackers.get(server_id)
    if tracker is not None:
        tracker.poke()


def is_join_leave_line(line: str) -> bool:
    # Paper colors join/leave messages: the codes would break the end-of-line match
    return JOIN_LEAVE_PATTERN.search(ansi.strip(line)) is not None


def stop_all() -> None:
    """Stop every tracker (tests, app exit)."""
    with _lock:
        ids = list(_trackers)
    for server_id in ids:
        stop_tracking(server_id)
