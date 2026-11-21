"""Cloning a server through the app core (pymcsc copies the folder)."""

import asyncio
from unittest import mock

import pytest

from mcsc import ServerBusyError, ServerConfig, ServerRunningError, ServerState, ServerType

from mcsc_gui.core import server_manager as sm
from test_backups import app, hashes, make_registered  # noqa: F401  pylint: disable=unused-import


def make_paper(app, server_id="srv", name="Survival"):  # noqa: F811
    server = make_registered(app, server_id, name)
    (server.path / "server.jar").write_bytes(b"paper jar")
    server.config.port = 25570
    server.config.jvm_args = ["-XX:+UseG1GC"]
    server.config.java_path = "java"
    return server


def make_forge(app, server_id="forge", libraries=True):  # noqa: F811
    path = app.manager.servers_dir / server_id
    install = path / "server"
    install.mkdir(parents=True)
    if libraries:
        (install / "libraries" / "net" / "minecraftforge" / "forge").mkdir(parents=True)
    (install / "server.properties").write_text("motd=forge\n", encoding="utf-8")
    config = ServerConfig("Modded", "1.20.1-47.3.0", ServerType.FORGE, ram_gb=6, id=server_id,
                          path=path)
    return app.manager.register(config)


def leftovers(app):  # noqa: F811
    return list(app.manager.servers_dir.glob("*.partial"))


def test_clone_copies_files_and_settings_but_not_backups(app):  # noqa: F811
    source = make_paper(app)
    sm.set_server_backup_policy(source, "on_stop")
    asyncio.run(sm.backup_server(source))
    app.events.clear()
    app.sent.clear()

    clone = asyncio.run(sm.clone_server(source, " Survival copy ", 5, accept_eula=True))

    assert clone.id != source.id and clone.path != source.path
    assert clone.path == app.manager.servers_dir / clone.id
    assert app.manager.find(clone.id) is clone
    assert hashes(clone.path) == hashes(source.path)
    assert clone.eula_accepted
    config = clone.config
    assert config.name == "Survival copy"
    assert config.ram_gb == 5
    assert (config.server_type, config.version) == (ServerType.PAPER, "1.21.4")
    assert (config.port, config.address, config.java_path, config.jvm_args) == \
        (25570, None, "java", ["-XX:+UseG1GC"])
    assert config.jvm_args is not source.config.jvm_args
    assert sm.server_backup_policy(clone) == "on_stop"
    assert sm.list_backups(clone) == []
    assert len(sm.list_backups(source)) == 1

    assert app.events == [("busy", "srv", True), ("busy", "srv", False), ("added", clone.id)]
    assert not sm.is_busy(source)
    event, details = app.sent[-1]
    assert event == "server_clone"
    assert details["source_uuid"] == "srv" and details["uuid"] == clone.id
    assert not any(isinstance(v, str) and str(app.tmp) in v for v in details.values())


def test_clone_without_eula_writes_false(app):  # noqa: F811
    source = make_paper(app)
    clone = asyncio.run(sm.clone_server(source, "Copy", 2, accept_eula=False))
    assert not clone.eula_accepted
    assert (clone.path / "eula.txt").read_text(encoding="utf-8").strip() == "eula=false"
    assert source.eula_accepted


def test_default_policy_is_not_copied_as_an_override(app):  # noqa: F811
    source = make_paper(app)
    clone = asyncio.run(sm.clone_server(source, "Copy", 2, accept_eula=True))
    assert sm.prefs.get(clone.id, "auto_backup") is None


def test_clone_forge_keeps_the_install_layout(app):  # noqa: F811
    source = make_forge(app)
    clone = asyncio.run(sm.clone_server(source, "Modded copy", 6, accept_eula=True))
    assert clone.server_dir == clone.path / "server"
    assert (clone.server_dir / "libraries" / "net" / "minecraftforge" / "forge").is_dir()
    assert (clone.server_dir / "server.properties").read_text(encoding="utf-8") == "motd=forge\n"


def test_unsupported_folder_is_reported_and_leaves_nothing(app):  # noqa: F811
    source = make_forge(app, libraries=False)
    with pytest.raises(sm.CloneNotSupportedError) as error:
        asyncio.run(sm.clone_server(source, "Copy", 2, accept_eula=True))
    assert sm.error_message(error.value) == "This server can't be cloned"
    assert len(app.manager) == 1
    assert leftovers(app) == []
    assert not sm.is_busy(source)


def test_failed_copy_is_rolled_back(app):  # noqa: F811
    source = make_paper(app)
    folders = set(app.manager.servers_dir.iterdir())
    with mock.patch("mcsc.manager.shutil.copytree", side_effect=OSError("disk error")), \
            pytest.raises(OSError):
        asyncio.run(sm.clone_server(source, "Copy", 2, accept_eula=True))
    assert len(app.manager) == 1
    assert set(app.manager.servers_dir.iterdir()) == folders
    assert not sm.is_busy(source)
    assert ("added",) not in [e[:1] for e in app.events]


def test_clone_refused_while_running_or_busy(app):  # noqa: F811
    source = make_paper(app)
    with pytest.raises(ValueError):
        asyncio.run(sm.clone_server(source, "  ", 2, accept_eula=True))

    source._state = ServerState.RUNNING  # pylint: disable=protected-access
    assert not sm.can_clone(source) and not sm.can_delete(source)
    assert sm.clone_block_reason(source) == "Stop the server to clone it"
    assert sm.delete_block_reason(source) == "Stop the server to delete it"
    with pytest.raises(ServerRunningError):
        asyncio.run(sm.clone_server(source, "Copy", 2, accept_eula=True))
    source._state = ServerState.STOPPED  # pylint: disable=protected-access

    sm._operations[source.id] = "backup"  # pylint: disable=protected-access
    try:
        assert sm.clone_block_reason(source) == "Backing up…"
        with pytest.raises(ServerBusyError):
            asyncio.run(sm.clone_server(source, "Copy", 2, accept_eula=True))
    finally:
        sm._operations.clear()  # pylint: disable=protected-access
    assert len(app.manager) == 1
    assert sm.can_clone(source) and sm.clone_block_reason(source) is None


def test_busy_server_is_never_started(app):  # noqa: F811
    source = make_paper(app)
    sm._operations[source.id] = "clone"  # pylint: disable=protected-access
    try:
        assert sm.activity_label(source) == "Cloning…"
        with mock.patch.object(source, "start", new=mock.AsyncMock()) as start:
            asyncio.run(sm.start_server(source))
        start.assert_not_called()
        assert app.notifier.messages[-1][0] == "error"
        assert app.notifier.messages[-1][1].startswith("Wait until")
    finally:
        sm._operations.clear()  # pylint: disable=protected-access


def test_suggested_name_and_size(app):  # noqa: F811
    source = make_paper(app)
    assert sm.suggest_clone_name(source) == "Survival (2)"
    make_paper(app, "other", "Survival (2)")
    assert sm.suggest_clone_name(source) == "Survival (3)"
    expected = sum(p.stat().st_size for p in source.path.rglob("*") if p.is_file())
    assert sm.server_size(source) == expected > 0


def test_server_size_of_a_missing_folder_is_zero(app):  # noqa: F811
    config = ServerConfig("Ghost", "1.21.4", ServerType.PAPER, id="ghost",
                          path=app.tmp / "missing")
    assert sm.server_size(app.manager.register(config)) == 0
