"""Backup, restore, export and import through the app core (pymcsc does the archiving)."""

import asyncio
import hashlib
import json
from pathlib import Path
from unittest import mock

import pytest

from mcsc import (
    BackupKind,
    IncompatibleBackupError,
    InsufficientDiskSpaceError,
    InvalidArchiveError,
    PaperServer,
    ServerBusyError,
    ServerConfig,
    ServerManager,
    ServerRunningError,
    ServerState,
    ServerType,
    UnsupportedArchiveVersionError,
)

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.notifier import set_notifier
from mcsc_gui.core.server_prefs import ServerPrefs
from mcsc_gui.core.user_settings import TYPES_CONVERTION


class Recorder:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("info", message))

    def success(self, message):
        self.messages.append(("success", message))

    def warning(self, message):
        self.messages.append(("warning", message))

    def error(self, message):
        self.messages.append(("error", message))


@pytest.fixture
def app(tmp_path: Path):
    """Isolated core: manager, prefs, settings, telemetry and notifier in tmp_path."""
    manager = ServerManager(tmp_path / "servers", tmp_path / "servers.json",
                            backups_dir=tmp_path / "backups", app_version="test")
    settings = {}
    events = []
    sent = []
    notifier = Recorder()

    async def fake_send(event, details=None):
        sent.append((event, details))

    callbacks = [
        (sm.on_server_added, lambda s: events.append(("added", s.id))),
        (sm.on_server_updated, lambda s: events.append(("updated", s.id))),
        (sm.on_server_busy_changed, lambda s: events.append(("busy", s.id, sm.is_busy(s)))),
        (sm.on_backups_changed, lambda s: events.append(("backups", s.id))),
    ]
    for register, callback in callbacks:
        register(callback)
    set_notifier(notifier)
    with mock.patch.object(sm, "manager", manager), \
            mock.patch.object(sm, "prefs", ServerPrefs(tmp_path / "prefs.json")), \
            mock.patch.object(sm, "_settings", lambda: settings), \
            mock.patch.object(sm, "send_event_async", fake_send):
        yield mock.Mock(manager=manager, settings=settings, events=events, sent=sent,
                        notifier=notifier, tmp=tmp_path)
    set_notifier(None)
    for _register, callback in callbacks:
        sm.remove_callback(callback)
    sm._attached.clear()  # pylint: disable=protected-access


def make_registered(app, server_id="srv", name="Survival"):
    path = app.manager.servers_dir / server_id
    (path / "world").mkdir(parents=True)
    (path / "eula.txt").write_text("eula=true\n", encoding="utf-8")
    (path / "server.properties").write_text("motd=hello\n", encoding="utf-8")
    (path / "world" / "level.dat").write_bytes(b"\x00level" * 100)
    (path / "logs").mkdir()
    (path / "logs" / "latest.log").write_text("log\n", encoding="utf-8")
    config = ServerConfig(name, "1.21.4", ServerType.PAPER, ram_gb=3, id=server_id, path=path)
    return app.manager.register(config)


def hashes(folder: Path) -> dict[str, str]:
    return {
        p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*")) if p.is_file() and "logs" not in p.parts
    }


# ------------------------------------------------------------------ policy


def test_policy_resolution(app):
    server = make_registered(app)
    assert sm.app_backup_policy() == "never"
    assert sm.server_backup_policy(server) == "default"
    assert sm.effective_backup_policy(server) == "never"

    app.settings["auto_backup"] = "on_stop"
    assert sm.effective_backup_policy(server) == "on_stop"

    sm.set_server_backup_policy(server, "on_start")
    assert sm.server_backup_policy(server) == "on_start"
    assert sm.effective_backup_policy(server) == "on_start"

    sm.set_server_backup_policy(server, "default")
    assert sm.effective_backup_policy(server) == "on_stop"
    with pytest.raises(ValueError):
        sm.set_server_backup_policy(server, "hourly")

    app.settings["auto_backup"] = "garbage"
    assert sm.app_backup_policy() == "never"


def test_retention_setting(app):
    assert sm.backup_retention() == 5
    app.settings["backup_retention"] = 2
    assert sm.backup_retention() == 2
    app.settings["backup_retention"] = "x"
    assert sm.backup_retention() == 5


def test_user_settings_conversions():
    assert TYPES_CONVERTION["auto_backup"](" On_Stop ") == "on_stop"
    assert TYPES_CONVERTION["backup_retention"]("3") == 3
    with pytest.raises(ValueError):
        TYPES_CONVERTION["auto_backup"]("always")
    with pytest.raises(ValueError):
        TYPES_CONVERTION["backup_retention"](-1)


def test_update_server_saves_policy_only_when_given(app):
    server = make_registered(app)
    sm.update_server(server, "A", 2)
    assert sm.server_backup_policy(server) == "default"
    sm.update_server(server, "A", 2, auto_backup="on_stop")
    assert sm.server_backup_policy(server) == "on_stop"


def test_server_prefs_persist_and_remove(tmp_path):
    path = tmp_path / "config" / "prefs.json"
    prefs = ServerPrefs(path)
    prefs.set("a", "auto_backup", "on_stop")
    prefs.set("b", "auto_backup", "never")
    assert ServerPrefs(path).get("a", "auto_backup") == "on_stop"
    prefs.remove("a")
    prefs.set("b", "auto_backup", None)
    assert json.loads(path.read_text(encoding="utf-8")) == {}
    path.write_text("not json", encoding="utf-8")
    assert ServerPrefs(path).get("a", "auto_backup", "default") == "default"


def test_error_messages_for_backup_errors():
    assert sm.error_message(InsufficientDiskSpaceError("x")) == \
        "Not enough disk space"
    assert sm.error_message(UnsupportedArchiveVersionError("x")) == \
        "This archive was created by a newer version of MCSC"
    assert sm.error_message(InvalidArchiveError("x")) == \
        "This file is not a valid MCSC backup or export"
    assert sm.error_message(IncompatibleBackupError("x")) == \
        "This backup belongs to a different server type"
    assert sm.error_message(ServerBusyError("x")).startswith("Wait until")


# ------------------------------------------------------------------ backup


def test_manual_backup_lists_fires_callbacks_and_telemetry(app):
    server = make_registered(app)
    progress = []
    backup = asyncio.run(sm.backup_server(server, progress=lambda d, t: progress.append((d, t))))

    assert backup.kind is BackupKind.MANUAL
    assert backup.path.parent == app.tmp / "backups" / "srv"
    assert [b.id for b in sm.list_backups(server)] == [backup.id]
    assert progress[-1][0] == progress[-1][1] > 0
    assert ("busy", "srv", True) in app.events
    assert app.events[-1] == ("backups", "srv")
    assert not sm.is_busy(server)
    event, details = app.sent[-1]
    assert event == "server_backup" and details["kind"] == "manual"
    assert not any("path" in key for key in details)


def test_backup_refused_while_running(app):
    server = make_registered(app)
    server._state = ServerState.RUNNING  # pylint: disable=protected-access
    assert not sm.can_backup(server)
    with pytest.raises(ServerRunningError):
        asyncio.run(sm.backup_server(server))
    assert not sm.is_busy(server)
    assert sm.list_backups(server) == []


def test_busy_server_cant_start_or_be_backed_up_twice(app):
    server = make_registered(app)
    sm._operations[server.id] = "backup"  # pylint: disable=protected-access
    try:
        assert sm.is_busy(server) and not sm.can_start(server) and not sm.can_backup(server)
        assert sm.activity_label(server) == "Backing up…"
        assert sm.any_operation_running()
        with pytest.raises(ServerBusyError):
            asyncio.run(sm.backup_server(server))
        with pytest.raises(ServerBusyError):
            asyncio.run(sm.delete_server(server, delete_files=False))
    finally:
        sm._operations.clear()  # pylint: disable=protected-access
    assert sm.can_start(server)


def test_delete_backup(app):
    server = make_registered(app)
    backup = asyncio.run(sm.backup_server(server))
    sm.delete_backup(backup)
    assert not backup.path.exists()
    assert sm.list_backups(server) == []
    assert app.events[-1] == ("backups", "srv")


# ----------------------------------------------------------------- automatic


def test_auto_backup_prunes_only_automatic_backups(app):
    server = make_registered(app)
    app.settings["backup_retention"] = 2
    manual = asyncio.run(sm.backup_server(server))
    for _ in range(4):
        assert asyncio.run(sm.auto_backup(server)) is not None

    backups = sm.list_backups(server)
    kinds = [b.kind for b in backups]
    assert kinds.count(BackupKind.AUTOMATIC) == 2
    assert manual.id in [b.id for b in backups]


def test_failed_auto_backup_is_only_a_warning(app):
    server = make_registered(app)
    server._state = ServerState.RUNNING  # pylint: disable=protected-access
    assert asyncio.run(sm.auto_backup(server)) is None
    level, message = app.notifier.messages[-1]
    assert level == "warning" and "Survival" in message


def test_start_with_on_start_policy_backs_up_first(app):
    server = make_registered(app)
    app.settings["auto_backup"] = "on_start"
    order = []

    async def fake_start():
        order.append(("start", len(sm.list_backups(server))))

    with mock.patch.object(server, "start", fake_start):
        asyncio.run(sm.start_server(server))
    assert order == [("start", 1)]
    assert sm.list_backups(server)[0].kind is BackupKind.AUTOMATIC


def test_failed_on_start_backup_doesnt_block_start(app):
    server = make_registered(app)
    sm.set_server_backup_policy(server, "on_start")
    started = []

    async def fake_start():
        started.append(True)

    with mock.patch.object(server, "start", fake_start), \
            mock.patch.object(app.manager, "backup_async", side_effect=OSError("disk")):
        asyncio.run(sm.start_server(server))
    assert started == [True]
    assert app.notifier.messages[-1][0] == "warning"


def test_on_stop_policy_backs_up_after_the_server_stops(app):
    server = make_registered(app)
    sm.set_server_backup_policy(server, "on_stop")

    async def scenario():
        await sm._on_state_change(server, ServerState.RUNNING,  # pylint: disable=protected-access
                                  ServerState.STOPPED)
        assert sm.pending_backups() == 1
        await sm.wait_pending_backups()

    asyncio.run(scenario())
    assert sm.pending_backups() == 0
    assert [b.kind for b in sm.list_backups(server)] == [BackupKind.AUTOMATIC]


def test_never_policy_doesnt_back_up(app):
    server = make_registered(app)

    async def scenario():
        await sm._on_state_change(server, ServerState.RUNNING,  # pylint: disable=protected-access
                                  ServerState.STOPPED)

    asyncio.run(scenario())
    assert sm.pending_backups() == 0
    assert sm.list_backups(server) == []


# --------------------------------------------------------- restore / export


def test_restore_is_lossless_and_keeps_a_safety_backup(app):
    server = make_registered(app)
    before = hashes(server.path)
    backup = asyncio.run(sm.backup_server(server))

    (server.path / "server.properties").write_text("motd=changed\n", encoding="utf-8")
    (server.path / "world" / "level.dat").unlink()
    server.config.version = "1.21.5"

    safety = asyncio.run(sm.restore_backup(server, backup))

    assert hashes(server.path) == before
    assert server.config.version == "1.21.4"
    assert safety is not None and safety.kind is BackupKind.BEFORE_RESTORE
    assert ("updated", "srv") in app.events
    assert app.sent[-1][0] == "server_restore"


def test_restore_refuses_another_server_type(app):
    server = make_registered(app)
    backup = asyncio.run(sm.backup_server(server))
    other = PaperServer(ServerConfig("Other", "1.21.4", ServerType.PAPER, id="o",
                                     path=app.tmp / "o"))
    other.config.server_type = ServerType.VANILLA
    with pytest.raises(IncompatibleBackupError):
        asyncio.run(sm.restore_backup(other, backup))


def test_export_import_round_trip(app):
    server = make_registered(app)
    dest = app.tmp / "out" / "survival.zip"
    manifest = asyncio.run(sm.export_server(server, dest))
    assert dest.is_file() and manifest.kind is BackupKind.EXPORT
    assert app.sent[-1][0] == "server_export"

    info = sm.inspect_archive(dest)
    assert info.suggested_name == "Survival (2)"
    assert info.eula_accepted

    imported = asyncio.run(sm.import_server(dest, info.suggested_name, 2, accept_eula=True))
    assert imported.id != server.id
    assert imported.name == "Survival (2)"
    assert imported.config.ram_gb == 2
    assert hashes(imported.path) == hashes(server.path) | {
        "eula.txt": hashes(imported.path)["eula.txt"]}
    assert ("added", imported.id) in app.events
    assert app.sent[-1][0] == "server_import"
    assert app.sent[-1][1]["source"] == "archive"


def test_import_rejects_invalid_archive(app):
    bogus = app.tmp / "bogus.zip"
    bogus.write_bytes(b"not a zip")
    with pytest.raises(InvalidArchiveError):
        sm.inspect_archive(bogus)
    with pytest.raises(InvalidArchiveError):
        asyncio.run(sm.import_server(bogus, "X", 2, accept_eula=False))
    assert len(app.manager) == 0


def test_import_folder_copies_the_server(app, tmp_path):
    source = tmp_path / "external"
    source.mkdir()
    (source / "paper-1.21.4.jar").write_bytes(b"jar")
    (source / "version_history.json").write_text(
        json.dumps({"currentVersion": "git-Paper-100 (MC: 1.21.4)"}), encoding="utf-8")
    detected = sm.detect_folder(source)
    assert detected.server_type is ServerType.PAPER and detected.version == "1.21.4"

    server = asyncio.run(sm.import_server_folder(source, detected.server_type, detected.version,
                                                 "External", 2, False, jar=detected.jar))
    assert (server.path / "server.jar").is_file()
    assert (source / "paper-1.21.4.jar").is_file()  # copied, never moved
    assert app.sent[-1][1]["source"] == "folder"


def test_delete_server_can_remove_backups_and_prefs(app):
    server = make_registered(app)
    sm.set_server_backup_policy(server, "on_stop")
    backup = asyncio.run(sm.backup_server(server))
    asyncio.run(sm.delete_server(server, delete_files=True, delete_backups=True))
    assert not backup.path.exists()
    assert sm.prefs.get("srv", "auto_backup") is None


def test_cleanup_never_raises(app):
    with mock.patch.object(app.manager, "cleanup_temporary_files", side_effect=OSError("x")):
        sm.cleanup_temporary_files()
