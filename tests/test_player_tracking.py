"""Player tracking in the server manager: preference, Query turned on at start, trackers."""

from mcsc import ServerState

from mcsc_gui.core import players
from mcsc_gui.core import server_manager as sm
from test_backups import app, make_registered  # noqa: F401  pylint: disable=unused-import
from test_clone import make_paper


def test_tracking_is_on_by_default_and_can_be_turned_off(app):  # noqa: F811
    server = make_registered(app)
    assert sm.player_tracking_enabled(server)
    assert sm.prefs.get(server.id, sm.PLAYER_TRACKING_PREF) is None  # no migration needed

    sm.set_player_tracking(server, False)
    assert not sm.player_tracking_enabled(server)
    assert ("updated", server.id) in app.events
    assert not sm.manages_query_keys(server, "server.properties")

    sm.update_server(server, "Survival", 2, player_tracking=True)
    assert sm.player_tracking_enabled(server)
    assert sm.prefs.get(server.id, sm.PLAYER_TRACKING_PREF) is None
    assert sm.manages_query_keys(server, "server.properties")
    assert not sm.manages_query_keys(server, "ops.json")


async def test_start_turns_query_on_for_existing_servers(app, monkeypatch):  # noqa: F811
    server = make_registered(app)
    (server.server_dir / "server.properties").write_text(
        "motd=hello\nenable-query=false\nserver-port=25566\n", encoding="utf-8")

    async def fake_start():
        server._set_state(ServerState.STARTING)  # pylint: disable=protected-access

    monkeypatch.setattr(server, "start", fake_start)
    await sm.start_server(server)
    props = server.read_properties()
    assert props["enable-query"] == "true" and props["query.port"] == "25566"
    assert props["motd"] == "hello"


async def test_start_leaves_properties_alone_when_tracking_is_off(app, monkeypatch):  # noqa: F811
    server = make_registered(app)
    sm.set_player_tracking(server, False)
    path = server.server_dir / "server.properties"
    path.write_text("motd=hello\nenable-query=false\n", encoding="utf-8")

    async def fake_start():
        server._set_state(ServerState.STARTING)  # pylint: disable=protected-access

    monkeypatch.setattr(server, "start", fake_start)
    await sm.start_server(server)
    assert path.read_text(encoding="utf-8") == "motd=hello\nenable-query=false\n"


async def test_trackers_follow_the_server_state(app):  # noqa: F811
    server = make_registered(app)
    sm.set_player_tracking(server, False)
    await sm._on_state_change(server, ServerState.STARTING,  # pylint: disable=protected-access
                              ServerState.RUNNING)
    assert players.is_tracking(server.id)
    assert players.uses_query(server.id) is False
    await sm._on_state_change(server, ServerState.RUNNING,  # pylint: disable=protected-access
                              ServerState.STOPPING)
    assert not players.is_tracking(server.id)


async def test_join_line_pokes_the_tracker(app, monkeypatch):  # noqa: F811
    server = make_registered(app)
    poked = []
    monkeypatch.setattr(players, "poke", poked.append)
    sm._on_output(server, "[10:00:00] [Server thread/INFO]: Steve joined the game")  # pylint: disable=protected-access
    sm._on_output(server, "[10:00:01] [Server thread/INFO]: Done (3.1s)!")  # pylint: disable=protected-access
    assert poked == [server.id]


async def test_clone_keeps_tracking_off(app):  # noqa: F811
    source = make_paper(app)
    sm.set_player_tracking(source, False)
    copy = await sm.clone_server(source, "Copy", 2, accept_eula=True)
    assert not sm.player_tracking_enabled(copy)
