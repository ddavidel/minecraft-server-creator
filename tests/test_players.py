import asyncio
import time
from pathlib import Path

import pytest

from mcsc import PaperServer, ServerConfig, ServerType

from mcsc_gui.core import players
from mcsc_gui.core.players import PlayerStatus, PlayerTracker


@pytest.fixture
def server(tmp_path: Path):
    return PaperServer(ServerConfig("Test", "1.21.4", ServerType.PAPER, id="srv",
                                    path=tmp_path / "srv", port=25570))


@pytest.fixture(autouse=True)
def _clean_registry():
    yield
    players.stop_all()
    with players._lock:  # pylint: disable=protected-access
        players._statuses.clear()  # pylint: disable=protected-access


def write_props(server, text):
    server.server_dir.mkdir(parents=True, exist_ok=True)
    (server.server_dir / "server.properties").write_text(text, encoding="utf-8")


def read_props(server):
    return (server.server_dir / "server.properties").read_text(encoding="utf-8")


# ----------------------------------------------------- ensure_query_enabled


def test_missing_file_gets_a_minimal_one(server):
    assert players.ensure_query_enabled(server) is True
    # No server.properties yet: the port registered in MCSC is used
    assert server.read_properties() == {"enable-query": "true", "query.port": "25570"}


def test_disabled_query_is_turned_on_with_the_server_port(server):
    write_props(server, "#Minecraft server properties\nmotd=Hi\nenable-query=false\n"
                        "query.port=25565\nserver-port=25566\nmax-players=7\n")
    assert players.ensure_query_enabled(server) is True
    props = server.read_properties()
    assert props["enable-query"] == "true"
    assert props["query.port"] == "25566"
    # Other keys and the leading comment are untouched
    assert props["motd"] == "Hi" and props["max-players"] == "7"
    assert read_props(server).startswith("#Minecraft server properties\n")


def test_default_server_port_when_missing(server):
    write_props(server, "motd=Hi\n")
    players.ensure_query_enabled(server)
    assert server.read_properties()["query.port"] == "25565"


def test_no_write_when_already_correct(server):
    write_props(server, "enable-query=true\nquery.port=25565\nserver-port=25565\n")
    path = server.server_dir / "server.properties"
    before = path.stat().st_mtime_ns
    assert players.ensure_query_enabled(server) is False
    assert path.stat().st_mtime_ns == before


def test_query_target_uses_server_ip_and_ports(server):
    write_props(server, "server-ip=192.168.1.5\nserver-port=25600\nquery.port=25601\n")
    assert players.query_target(server) == ("192.168.1.5", 25601, 25600)
    write_props(server, "server-ip=\nserver-port=25600\n")
    assert players.query_target(server) == ("127.0.0.1", 25600, 25600)


def test_status_label():
    assert PlayerStatus(3, 20).label() == "3 / 20"
    assert PlayerStatus().label() == "–"
    assert not PlayerStatus().known


def test_join_leave_lines():
    assert players.is_join_leave_line("[12:00:01] [Server thread/INFO]: Steve joined the game")
    assert players.is_join_leave_line(
        "[12:00:01] [Server thread/INFO] [minecraft/MinecraftServer]: Alex left the game")
    assert not players.is_join_leave_line("[12:00:01] [Server thread/INFO]: <Steve> hi all")
    assert not players.is_join_leave_line(
        "[12:00:01] [Server thread/INFO]: <Steve> someone joined the game")


# ------------------------------------------------------------ PlayerTracker


def fetcher(result):
    calls = []

    async def fetch(host, port, timeout):
        calls.append((host, port))
        if isinstance(result, Exception):
            raise result
        return result

    fetch.calls = calls
    return fetch


async def test_query_ok(server):
    write_props(server, "server-port=25570\nquery.port=25570\n")
    query = fetcher(PlayerStatus(2, 20, ("Alex", "Steve"), source="query"))
    ping = fetcher(PlayerStatus(2, 20, source="status"))
    tracker = PlayerTracker(server, lambda *_: None, query=query, ping=ping)
    status = await tracker.poll()
    assert status.source == "query" and status.names == ("Alex", "Steve")
    assert query.calls == [("127.0.0.1", 25570)] and ping.calls == []


async def test_query_fails_falls_back_to_status(server):
    query = fetcher(OSError("timed out"))
    ping = fetcher(PlayerStatus(1, 20, ("Steve",), partial=True, source="status"))
    status = await PlayerTracker(server, lambda *_: None, query=query, ping=ping).poll()
    assert status.source == "status" and status.partial and status.online == 1


async def test_tracking_off_uses_only_status(server):
    query = fetcher(PlayerStatus(5, 20, source="query"))
    ping = fetcher(PlayerStatus(1, 20, source="status"))
    status = await PlayerTracker(server, lambda *_: None, use_query=False,
                                 query=query, ping=ping).poll()
    assert status.source == "status" and query.calls == []


async def test_both_fail_unknown_and_warns_once(server, caplog):
    tracker = PlayerTracker(server, lambda *_: None, query=fetcher(OSError("x")),
                            ping=fetcher(ConnectionRefusedError()))
    first = await tracker.poll()
    await tracker.poll()
    assert not first.known and first.source == "none"
    assert len([r for r in caplog.records if "Can't read the players" in r.message]) == 1


async def test_start_publishes_and_stop_clears(server):
    received = []
    players.add_listener(lambda sid, status: received.append((sid, status.online)))
    try:
        players.start_tracking(server, query=fetcher(PlayerStatus(3, 20, source="query")),
                               ping=fetcher(OSError()), interval=10)
        for _ in range(50):
            if received:
                break
            await asyncio.sleep(0.01)
        assert received == [("srv", 3)]
        assert players.status("srv").online == 3
        assert players.is_tracking("srv") and players.uses_query("srv") is True
        players.stop_tracking("srv")
        assert received[-1] == ("srv", None)
        assert players.status("srv") == players.NO_PLAYERS
        assert not players.is_tracking("srv") and players.uses_query("srv") is None
    finally:
        players._listeners.clear()  # pylint: disable=protected-access


async def test_poke_polls_again_debounced(server):
    count = 0

    async def query(host, port, timeout):
        nonlocal count
        count += 1
        return PlayerStatus(count, 20, source="query")

    tracker = PlayerTracker(server, lambda *_: None, query=query, ping=fetcher(OSError()),
                            interval=60, debounce=0.05)
    tracker.start()
    try:
        await asyncio.sleep(0.02)
        assert count == 1
        for _ in range(5):  # a burst of join lines -> one extra poll
            tracker.poke()
        await asyncio.sleep(0.15)
        assert count == 2
    finally:
        tracker.stop()


def test_same_status_is_not_published_twice():
    received = []
    players.add_listener(lambda sid, status: received.append(status.online))
    try:
        players._publish("a", PlayerStatus(1, 20, updated_at=time.time()))  # pylint: disable=protected-access
        players._publish("a", PlayerStatus(1, 20, updated_at=time.time() + 5))  # pylint: disable=protected-access
        players._publish("a", PlayerStatus(2, 20))  # pylint: disable=protected-access
        assert received == [1, 2]
        assert players.names("a") == ()
    finally:
        players._listeners.clear()  # pylint: disable=protected-access
