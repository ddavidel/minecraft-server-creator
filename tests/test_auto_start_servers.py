"""Servers started automatically when the app opens (``auto_start`` server preference)."""

import asyncio

import pytest

from mcsc import ServerState

from mcsc_gui.core import server_manager as sm
from test_backups import app, make_registered  # noqa: F401  pylint: disable=unused-import
from test_clone import make_paper


@pytest.fixture
def no_wait(monkeypatch):
    monkeypatch.setattr(sm, "AUTO_START_WAIT", 0)


def test_auto_start_preference(app):  # noqa: F811
    server = make_registered(app)
    assert not sm.server_auto_start(server)

    sm.set_server_auto_start(server, True)
    assert sm.server_auto_start(server)
    assert ("updated", server.id) in app.events

    sm.update_server(server, "Renamed", 2, auto_start=False)
    assert not sm.server_auto_start(server)
    assert sm.prefs.get(server.id, sm.AUTO_START_PREF) is None  # nothing left behind

    sm.update_server(server, "Renamed", 2, auto_start=True)
    sm.update_server(server, "Renamed again", 2)  # None: unchanged
    assert sm.server_auto_start(server)


async def test_auto_start_servers_in_order_skipping_and_continuing(app, monkeypatch,  # noqa: F811
                                                                   no_wait):
    first = make_registered(app, "a", "First")
    manual = make_registered(app, "b", "Manual")
    broken = make_registered(app, "c", "Broken")
    last = make_registered(app, "d", "Last")
    for server in (first, broken, last):
        sm.set_server_auto_start(server, True)
    assert sm.auto_start_candidates() == [first, broken, last]
    assert manual not in sm.auto_start_candidates()

    calls = []

    async def fake_start(server):
        calls.append(server.id)
        if server is broken:
            raise RuntimeError("boom")
        server._set_state(ServerState.RUNNING)  # pylint: disable=protected-access

    monkeypatch.setattr(sm, "start_server", fake_start)
    started = await sm.auto_start_servers()

    assert calls == ["a", "c", "d"]
    assert started == [first, last]
    assert any(level == "error" for level, _msg in app.notifier.messages)

    calls.clear()
    assert await sm.auto_start_servers() == []  # already running: skipped
    assert calls == ["c"]


async def test_auto_start_waits_for_each_server(app, monkeypatch):  # noqa: F811
    first = make_registered(app, "a", "First")
    second = make_registered(app, "b", "Second")
    sm.set_server_auto_start(first, True)
    sm.set_server_auto_start(second, True)
    monkeypatch.setattr(sm, "AUTO_START_POLL", 0.01)
    order = []

    async def fake_start(server):
        order.append(("start", server.id, first.state))
        server._set_state(ServerState.STARTING)  # pylint: disable=protected-access

        async def ready():
            await asyncio.sleep(0.05)
            server._set_state(ServerState.RUNNING)  # pylint: disable=protected-access

        asyncio.ensure_future(ready())

    monkeypatch.setattr(sm, "start_server", fake_start)
    await sm.auto_start_servers()
    # The second server started only once the first one was running
    assert order == [("start", "a", ServerState.STOPPED), ("start", "b", ServerState.RUNNING)]


async def test_auto_start_telemetry_trigger(app):  # noqa: F811
    server = make_registered(app)
    sm._auto_starting.add(server.id)  # pylint: disable=protected-access
    try:
        await sm._on_state_change(  # pylint: disable=protected-access
            server, ServerState.STOPPED, ServerState.STARTING)
    finally:
        sm._auto_starting.discard(server.id)  # pylint: disable=protected-access
    await sm._on_state_change(  # pylint: disable=protected-access
        server, ServerState.STOPPED, ServerState.STARTING)
    starts = [d for e, d in app.sent if e == "server_start"]
    assert starts[0]["trigger"] == "auto"
    assert "trigger" not in starts[1]


async def test_clone_does_not_inherit_auto_start(app):  # noqa: F811
    source = make_paper(app)
    sm.set_server_auto_start(source, True)
    copy = await sm.clone_server(source, "Copy", 2, accept_eula=True)
    assert not sm.server_auto_start(copy)
