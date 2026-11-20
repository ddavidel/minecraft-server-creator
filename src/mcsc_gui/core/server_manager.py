"""
Bridge between the GUI and the pymcsc library (imported as ``mcsc``).

pymcsc owns everything about servers (registry, install, process, monitoring,
config files, backups). This module adds what the library deliberately leaves to
the app: the shared ``ServerManager`` instance, telemetry, translated labels and
errors, user notifications and the automatic backup policy.

It must not import any UI toolkit: errors are reported through
:func:`mcsc_gui.core.notifier.get_notifier` and registry changes through the
``on_server_added`` / ``on_server_removed`` / ``on_server_updated`` callbacks;
backups through ``on_backups_changed`` and running operations (backup, restore,
export...) through ``on_server_busy_changed``.
Callbacks may run in the asyncio bridge thread.

Backups, restore, export and import are done by pymcsc (archives in
``BACKUPS_DIR_PATH/<server id>/``); the app adds the automatic backup policy
(app-wide setting + per-server override in :mod:`mcsc_gui.core.server_prefs`),
retention, telemetry and notifications.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import logging
import os
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from mcsc import (
    ArchiveInfo,
    Backup,
    BackupError,
    BackupKind,
    BackupManifest,
    DetectedServer,
    DownloadError,
    EulaNotAcceptedError,
    IncompatibleBackupError,
    InstallError,
    InsufficientDiskSpaceError,
    InvalidArchiveError,
    InvalidServerFolderError,
    JavaNotFoundError,
    MCSCError,
    MinecraftServer,
    ServerBusyError,
    ServerConfig,
    ServerManager,
    ServerNotFoundError,
    ServerNotRunningError,
    ServerRunningError,
    ServerState,
    ServerType,
    UnsupportedArchiveVersionError,
    UnsupportedVersionError,
    VersionNotFoundError,
    detect_server_folder,
)

from mcsc_gui.config import settings as mcssettings
from mcsc_gui.core.notifier import get_notifier, notify_warning
from mcsc_gui.core.os_utils import local_ip_address
from mcsc_gui.core.server_prefs import ServerPrefs
from mcsc_gui.core.translations import translate as _
from mcsc_gui.core.user_settings import (
    AUTO_BACKUP_POLICIES,
    DEFAULT_AUTO_BACKUP,
    DEFAULT_BACKUP_RETENTION,
    UserSettings,
)
from mcsc_gui.telemetry import send_event_async

logger = logging.getLogger(__name__)


def _app_version() -> str | None:
    """App version written in backup manifests."""
    try:
        return importlib.metadata.version(mcssettings.PACKAGE_NAME)
    except importlib.metadata.PackageNotFoundError:
        return None


manager = ServerManager(
    mcssettings.SERVER_DIR_PATH,
    mcssettings.SERVERS_JSON_PATH,
    output_buffer=mcssettings.MAX_LOG_LINES,
    backups_dir=mcssettings.BACKUPS_DIR_PATH,
    app_version=_app_version(),
)

# Per-server app preferences (automatic backup override)
prefs = ServerPrefs(mcssettings.SERVER_PREFS_PATH)

# Options for the "Server Type" selects: {0: "Vanilla", 1: "Paper", 2: "Forge"}
SERVER_TYPES: dict[int, str] = {int(t): t.label for t in ServerType}

STATE_LABELS: dict[ServerState, str] = {
    ServerState.STOPPED: "Stopped",
    ServerState.STARTING: "Starting",
    ServerState.RUNNING: "Running",
    ServerState.STOPPING: "Stopping",
}

# Automatic backup policy of a server: "default" follows the app setting
DEFAULT_POLICY = "default"
SERVER_BACKUP_POLICIES: tuple[str, ...] = (DEFAULT_POLICY, *AUTO_BACKUP_POLICIES)
BACKUP_POLICY_LABELS: dict[str, str] = {
    DEFAULT_POLICY: "Use app default",
    "never": "Never",
    "on_start": "When the server starts",
    "on_stop": "When the server stops",
}

BACKUP_KIND_LABELS: dict[BackupKind, str] = {
    BackupKind.MANUAL: "Manual",
    BackupKind.AUTOMATIC: "Automatic",
    BackupKind.BEFORE_RESTORE: "Before restore",
    BackupKind.BEFORE_UPGRADE: "Before upgrade",
    BackupKind.EXPORT: "Export",
}

# What a busy server is doing (pymcsc operation names + the app's own)
OPERATION_LABELS: dict[str, str] = {
    "backup": "Backing up…",
    "restore": "Restoring…",
    "export": "Exporting…",
    "delete": "Deleting…",
    "delete backup": "Deleting…",
}

# Most specific first: the first matching type wins.
ERROR_MESSAGES: tuple[tuple[type[MCSCError], str], ...] = (
    (ServerBusyError, "Wait until the current operation on this server is finished"),
    (EulaNotAcceptedError, "EULA not accepted"),
    (ServerRunningError, "Can't do this while the server is running"),
    (ServerNotRunningError, "The server is not running"),
    (ServerNotFoundError, "Invalid server"),
    (JavaNotFoundError, "Java not found. Install Java and try again"),
    (UnsupportedVersionError, "Unsupported Forge Version. THIS IS NOT A BUG!"),
    (VersionNotFoundError, "Version URL not found"),
    (DownloadError, "Download failed. Check your internet connection"),
    (InstallError, "Server installation failed"),
    (InsufficientDiskSpaceError, "Not enough disk space for the backup"),
    (UnsupportedArchiveVersionError, "This archive was created by a newer version of MCSC"),
    (InvalidArchiveError, "This file is not a valid MCSC backup or export"),
    (IncompatibleBackupError, "This backup belongs to a different server type"),
    (InvalidServerFolderError, "This folder doesn't look like a Minecraft server"),
    (BackupError, "The backup operation failed"),
)

_attached: set[str] = set()

ServerCallback = Callable[[MinecraftServer], Any]
_added_callbacks: list[ServerCallback] = []
_removed_callbacks: list[ServerCallback] = []
_updated_callbacks: list[ServerCallback] = []
_busy_callbacks: list[ServerCallback] = []
_backups_callbacks: list[ServerCallback] = []

# Operations started by the app, by server id ("backup", "restore", ...). pymcsc
# marks a server busy only once its worker runs; this covers the whole call.
_operations: dict[str, str] = {}
_operations_lock = threading.Lock()
# Automatic backups scheduled when a server stopped ("on_stop" policy)
_pending_backups: set[asyncio.Future] = set()


# --------------------------------------------------------------- callbacks


def on_server_added(callback: ServerCallback) -> None:
    """Call ``callback(server)`` after a server is created or registered."""
    _added_callbacks.append(callback)


def on_server_removed(callback: ServerCallback) -> None:
    """Call ``callback(server)`` after a server is deleted."""
    _removed_callbacks.append(callback)


def on_server_updated(callback: ServerCallback) -> None:
    """Call ``callback(server)`` after a server's settings (name, RAM, version) change."""
    _updated_callbacks.append(callback)


def on_server_busy_changed(callback: ServerCallback) -> None:
    """Call ``callback(server)`` when an operation (backup, restore...) starts or ends on a server."""
    _busy_callbacks.append(callback)


def on_backups_changed(callback: ServerCallback) -> None:
    """Call ``callback(server)`` after a backup of the server is created or deleted."""
    _backups_callbacks.append(callback)


def remove_callback(callback: ServerCallback) -> None:
    """Unregister ``callback`` from every registry event."""
    for callbacks in (_added_callbacks, _removed_callbacks, _updated_callbacks,
                      _busy_callbacks, _backups_callbacks):
        while callback in callbacks:
            callbacks.remove(callback)


def _fire(callbacks: list[ServerCallback], server: MinecraftServer) -> None:
    for callback in list(callbacks):
        try:
            callback(server)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception(f"Server callback {callback!r} failed")


# ------------------------------------------------------------------ helpers


def status_label(state: ServerState) -> str:
    """Translated, display friendly server state."""
    return _(STATE_LABELS[ServerState(state)])


def error_message(error: Exception) -> str:
    """Translated message for an error raised by pymcsc (or any other error)."""
    for error_type, message in ERROR_MESSAGES:
        if isinstance(error, error_type):
            return _(message)
    return str(error)


def server_operation(server: MinecraftServer) -> str | None:
    """Operation running on a server (``"backup"``, ``"restore"``...), ``None`` if idle."""
    with _operations_lock:
        operation = _operations.get(server.id)
    return operation or server.operation


def is_busy(server: MinecraftServer) -> bool:
    """True while a backup, restore, export or delete runs on the server."""
    return server_operation(server) is not None


def activity_label(server: MinecraftServer) -> str | None:
    """Translated label of the running operation ("Backing up…"), ``None`` if idle."""
    operation = server_operation(server)
    if operation is None:
        return None
    return _(OPERATION_LABELS.get(operation, "Busy…"))


def any_operation_running() -> bool:
    """True while a backup, restore, export or delete runs, or an automatic backup is pending."""
    with _operations_lock:
        if _operations:
            return True
    return bool(_pending_backups) or bool(manager.busy_servers)


def can_start(server: MinecraftServer) -> bool:
    """True when the start button should be enabled."""
    return not server.is_active and not is_busy(server)


def can_stop(server: MinecraftServer) -> bool:
    """True when the stop button should be enabled."""
    return server.state in (ServerState.STARTING, ServerState.RUNNING)


def can_backup(server: MinecraftServer) -> bool:
    """True when backup, export and restore are possible (stopped and idle server)."""
    return server.state is ServerState.STOPPED and not is_busy(server)


def backup_kind_label(kind: BackupKind | str) -> str:
    """Translated, display friendly backup kind."""
    return _(BACKUP_KIND_LABELS.get(BackupKind(kind), str(kind)))


def telemetry_details(server: MinecraftServer) -> dict[str, Any]:
    """Server info sent with telemetry events (same keys as the legacy settings, no local paths)."""
    config = server.config
    return {
        "uuid": config.id,
        "name": config.name,
        "version": config.version,
        "jar_type": int(config.server_type),
        "dedicated_ram": config.ram_gb,
        "port": config.port,
    }


def notify_error(error: Exception) -> None:
    """Show a translated error notification through the registered notifier."""
    get_notifier().error(error_message(error))


async def _send_event(event: str, details: dict[str, Any]) -> None:
    """Telemetry that never breaks the operation it reports."""
    try:
        await send_event_async(event, details=details)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning(f"Can't send telemetry event {event}: {e}")


# --------------------------------------------------------------- lifecycle


async def _on_state_change(server: MinecraftServer, old: ServerState, new: ServerState) -> None:
    """Server state listener: start/stop telemetry and the "on stop" automatic backup."""
    if new is ServerState.STARTING:
        await send_event_async("server_start", details=telemetry_details(server))
    elif new is ServerState.STOPPED and old is not ServerState.STOPPED:
        if effective_backup_policy(server) == "on_stop":
            _schedule_auto_backup(server)
        await send_event_async("server_stop", details=telemetry_details(server))


def _attach(server: MinecraftServer) -> MinecraftServer:
    """Register the app listeners on a server (once)."""
    if server.id not in _attached:
        server.add_state_listener(_on_state_change)
        _attached.add(server.id)
    return server


def load_servers() -> list[MinecraftServer]:
    """Load the servers registry (also reads the legacy servers.json format)."""
    logger.info("Loading servers...")
    servers = manager.load()
    for server in servers:
        _attach(server)
    return servers


def cleanup_temporary_files() -> None:
    """Remove leftovers of interrupted backups, restores and imports (call at startup). Never raises."""
    try:
        removed = manager.cleanup_temporary_files()
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Can't clean up the temporary backup files")
        return
    if removed:
        logger.info(f"Removed {len(removed)} leftover temporary files")


def register_server(config: ServerConfig) -> MinecraftServer:
    """Register an already installed server (used by the legacy migration)."""
    server = _attach(manager.register(config))
    _fire(_added_callbacks, server)
    return server


def get_servers() -> list[MinecraftServer]:
    """All registered servers."""
    return manager.servers


def find_server(uuid: str) -> MinecraftServer | None:
    """Server with the given id, ``None`` if it doesn't exist."""
    return manager.find(uuid)


def any_server_active() -> bool:
    """True if at least one server process is alive."""
    return bool(manager.active_servers)


def preload_versions() -> None:
    """Fetch the version lists at startup, so dialogs open instantly. Never raises."""
    try:
        manager.catalog.load()
    except MCSCError as e:
        logger.warning(f"Can't load server versions: {e}")


def get_versions(server_type: int | ServerType) -> list[str]:
    """Available versions for a server type, newest first (``[]`` if they can't be loaded)."""
    try:
        return manager.catalog.versions(
            ServerType(server_type),
            stable_only=mcssettings.JAR_VERSIONS_FILTER == "stable",
        )
    except MCSCError as e:
        logger.warning(f"Can't load versions for server type {server_type}: {e}")
        return []


async def create_server(
    name: str,
    version: str,
    server_type: int | ServerType,
    ram_gb: int,
    accept_eula: bool,
) -> MinecraftServer:
    """Download, install and register a new server without blocking the UI."""
    name = (name or "").strip()
    if not name:
        raise ValueError(_("Server name can't be empty"))
    if not version:
        raise ValueError(_("Server version can't be empty"))

    logger.info(f"Creating server {name!r} ({version})...")
    server = await manager.create_async(
        name,
        version,
        ServerType(server_type),
        accept_eula=accept_eula,
        ram_gb=int(ram_gb),
    )
    _attach(server)
    _fire(_added_callbacks, server)
    await send_event_async("server_create", details=telemetry_details(server))
    return server


def update_server(server: MinecraftServer, name: str, ram_gb: int,
                  auto_backup: str | None = None) -> None:
    """Change a server's editable settings and persist them.

    ``auto_backup`` (one of :data:`SERVER_BACKUP_POLICIES`) is the server's
    automatic backup override; ``None`` leaves it unchanged.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError(_("Server name can't be empty"))
    if auto_backup is not None:
        set_server_backup_policy(server, auto_backup)
    server.config.name = name
    server.config.ram_gb = int(ram_gb)
    manager.save()
    _fire(_updated_callbacks, server)


async def delete_server(server: MinecraftServer, delete_files: bool,
                        delete_backups: bool = False) -> None:
    """Unregister a stopped server, optionally deleting its folder and its backups."""
    _check_idle(server)
    details = telemetry_details(server)
    manager.delete(server, delete_files=delete_files, delete_backups=delete_backups)
    prefs.remove(server.id)
    _attached.discard(server.id)
    try:
        server.remove_state_listener(_on_state_change)
    except ValueError:
        pass
    _fire(_removed_callbacks, server)
    await send_event_async("server_delete", details=details)


async def start_server(server: MinecraftServer) -> None:
    """Start a server, notifying the user on failure.

    With the "on start" automatic backup policy the server is backed up first;
    a failed backup is only a warning, the server starts anyway.
    """
    if not server.is_active and not is_busy(server) \
            and effective_backup_policy(server) == "on_start":
        await auto_backup(server)
    try:
        await server.start()
    except MCSCError as e:
        logger.error(f"Can't start server {server.id}: {e}")
        notify_error(e)


async def stop_server(server: MinecraftServer) -> None:
    """Gracefully stop a server (killed after the timeout), notifying the user on failure."""
    if not server.is_active:
        return
    try:
        await server.stop(mcssettings.SERVER_STOP_TIMEOUT)
    except MCSCError as e:
        logger.error(f"Can't stop server {server.id}: {e}")
        notify_error(e)


async def send_command(server: MinecraftServer, command: str) -> None:
    """Send a console command; "stop" goes through :func:`stop_server`."""
    command = command.strip()
    if not command:
        return
    if command == server.STOP_COMMAND:
        await stop_server(server)
        return
    try:
        await server.send_command(command)
    except (MCSCError, ConnectionError) as e:
        notify_error(e)


async def stop_all_servers() -> None:
    """Stop every running server, then wait for their "on stop" automatic backups."""
    logger.info("Stopping all servers...")
    await manager.stop_all(mcssettings.SERVER_STOP_TIMEOUT)
    await asyncio.sleep(0)  # let the state listeners schedule the post-stop backups
    await wait_pending_backups()


def config_file_exists(server: MinecraftServer, filename: str) -> bool:
    """True if an editable config file exists in the server folder."""
    try:
        return server.config_file_path(filename).is_file()
    except ValueError:
        return False


# ------------------------------------------------------------------ backups


def _check_idle(server: MinecraftServer) -> None:
    operation = server_operation(server)
    if operation is not None:
        raise ServerBusyError(f"Server {server.name!r} is busy ({operation} in progress)")


@contextmanager
def _operation(server: MinecraftServer, name: str) -> Iterator[None]:
    """Mark ``server`` busy with ``name`` for the app (one operation per server)."""
    with _operations_lock:
        current = _operations.get(server.id) or server.operation
        if current is not None:
            raise ServerBusyError(f"Server {server.name!r} is busy ({current} in progress)")
        _operations[server.id] = name
    _fire(_busy_callbacks, server)
    try:
        yield
    finally:
        with _operations_lock:
            _operations.pop(server.id, None)
        _fire(_busy_callbacks, server)


def _settings() -> dict[str, Any]:
    """The current user settings (re-read, so changes apply without a restart)."""
    return UserSettings().user_settings


def app_backup_policy() -> str:
    """App-wide automatic backup policy: "never", "on_start" or "on_stop"."""
    value = _settings().get("auto_backup", DEFAULT_AUTO_BACKUP)
    return value if value in AUTO_BACKUP_POLICIES else DEFAULT_AUTO_BACKUP


def backup_retention() -> int:
    """How many automatic backups are kept per server (0 = unlimited)."""
    try:
        return max(0, int(_settings().get("backup_retention", DEFAULT_BACKUP_RETENTION)))
    except (TypeError, ValueError):
        return DEFAULT_BACKUP_RETENTION


def server_backup_policy(server: MinecraftServer) -> str:
    """The server's own policy: "default" (follow the app) or an override."""
    value = prefs.get(server.id, "auto_backup", DEFAULT_POLICY)
    return value if value in SERVER_BACKUP_POLICIES else DEFAULT_POLICY


def set_server_backup_policy(server: MinecraftServer, policy: str) -> None:
    """Set the server's automatic backup override ("default" removes it)."""
    if policy not in SERVER_BACKUP_POLICIES:
        raise ValueError(f"Invalid backup policy: {policy!r}")
    prefs.set(server.id, "auto_backup", None if policy == DEFAULT_POLICY else policy)


def effective_backup_policy(server: MinecraftServer) -> str:
    """The policy that applies to the server: its override, else the app setting."""
    policy = server_backup_policy(server)
    return app_backup_policy() if policy == DEFAULT_POLICY else policy


def list_backups(server: MinecraftServer) -> list[Backup]:
    """Backups of a server, newest first (what is on disk)."""
    try:
        return manager.list_backups(server)
    except OSError as e:
        logger.warning(f"Can't list the backups of server {server.id}: {e}")
        return []


def backups_folder(server: MinecraftServer) -> Path:
    """Folder of a server's backups (created, so it can be opened)."""
    folder = manager.backups_path(server)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


async def backup_server(server: MinecraftServer, kind: BackupKind | str = BackupKind.MANUAL,
                        *, progress: Callable[[int, int], Any] | None = None) -> Backup:
    """Back up a stopped server into its backups folder (in a worker thread).

    Other features (e.g. server upgrade) use ``kind="before_upgrade"``.
    """
    kind = BackupKind(kind)
    with _operation(server, "backup"):
        backup = await manager.backup_async(server, kind, progress=progress)
    logger.info(f"Backed up server {server.id} ({kind}): {backup.path.name}")
    _fire(_backups_callbacks, server)
    await _send_event("server_backup", {**telemetry_details(server), "kind": str(kind)})
    return backup


async def auto_backup(server: MinecraftServer) -> Backup | None:
    """Automatic backup + retention. Never raises: a failure is only a warning."""
    try:
        backup = await backup_server(server, BackupKind.AUTOMATIC)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning(f"Automatic backup of server {server.id} failed: {e!r}")
        notify_warning(_("Automatic backup of server '{name}' failed: {error}",
                         name=server.name, error=error_message(e)))
        return None
    try:
        removed = await asyncio.to_thread(manager.prune_backups, server, backup_retention())
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception(f"Can't prune the automatic backups of server {server.id}")
    else:
        if removed:
            _fire(_backups_callbacks, server)
    return backup


def _schedule_auto_backup(server: MinecraftServer) -> None:
    """Run :func:`auto_backup` in the background (see :func:`wait_pending_backups`)."""
    task = asyncio.ensure_future(auto_backup(server))
    _pending_backups.add(task)
    task.add_done_callback(_pending_backups.discard)


def pending_backups() -> int:
    """Automatic backups scheduled after a server stopped and not finished yet."""
    return len(_pending_backups)


async def wait_pending_backups() -> None:
    """Wait for the scheduled automatic backups (used when the app quits)."""
    while _pending_backups:
        logger.info(f"Waiting for {len(_pending_backups)} automatic backups...")
        await asyncio.gather(*list(_pending_backups), return_exceptions=True)


def delete_backup(backup: Backup) -> None:
    """Delete a backup archive. Blocking (call it with ``run_blocking``)."""
    server = find_server(backup.server_id)
    if server is None:
        manager.delete_backup(backup)
        return
    with _operation(server, "delete backup"):
        manager.delete_backup(backup)
    _fire(_backups_callbacks, server)


async def restore_backup(server: MinecraftServer, backup: Backup | str | os.PathLike[str], *,
                         progress: Callable[[int, int], Any] | None = None) -> Backup | None:
    """Replace a stopped server's files with a backup; returns the safety backup made first."""
    with _operation(server, "restore"):
        safety = await manager.restore_backup_async(server, backup, progress=progress)
    logger.info(f"Restored server {server.id}")
    _fire(_updated_callbacks, server)  # the version may have changed
    _fire(_backups_callbacks, server)  # new "before restore" backup
    details = telemetry_details(server)
    if isinstance(backup, Backup):
        details["kind"] = str(backup.kind)
    await _send_event("server_restore", details)
    return safety


async def export_server(server: MinecraftServer, dest: str | os.PathLike[str], *,
                        progress: Callable[[int, int], Any] | None = None) -> BackupManifest:
    """Export a stopped server to a ``.zip`` chosen by the user (same format as a backup)."""
    with _operation(server, "export"):
        manifest = await manager.export_async(server, dest, progress=progress)
    logger.info(f"Exported server {server.id}")
    await _send_event("server_export", telemetry_details(server))
    return manifest


def inspect_archive(archive: str | os.PathLike[str]) -> ArchiveInfo:
    """Preview of an MCSC export/backup before importing it. Blocking."""
    return manager.inspect_archive(archive)


def detect_folder(folder: str | os.PathLike[str]) -> DetectedServer:
    """Guess type, version and jar of an existing server folder. Blocking."""
    return detect_server_folder(folder)


def _check_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError(_("Server name can't be empty"))
    return name


async def import_server(archive: str | os.PathLike[str], name: str, ram_gb: int,
                        accept_eula: bool, *,
                        progress: Callable[[int, int], Any] | None = None) -> MinecraftServer:
    """Create a new server (new id and folder) from an MCSC export/backup."""
    name = _check_name(name)
    server = await manager.import_archive_async(
        archive, name=name, ram_gb=int(ram_gb), accept_eula=accept_eula, progress=progress
    )
    _attach(server)
    _fire(_added_callbacks, server)
    await _send_event("server_import", {**telemetry_details(server), "source": "archive"})
    return server


async def import_server_folder(folder: str | os.PathLike[str], server_type: int | ServerType,
                               version: str, name: str, ram_gb: int, accept_eula: bool,
                               jar: str | os.PathLike[str] | None = None) -> MinecraftServer:
    """Copy (never move) an existing server folder into a new registered server."""
    name = _check_name(name)
    version = (version or "").strip()
    if not version:
        raise ValueError(_("Server version can't be empty"))
    server = await manager.import_folder_async(
        folder, ServerType(server_type), version, name=name, ram_gb=int(ram_gb),
        accept_eula=accept_eula, jar=jar,
    )
    _attach(server)
    _fire(_added_callbacks, server)
    await _send_event("server_import", {**telemetry_details(server), "source": "folder"})
    return server


def connection_address(server: MinecraftServer) -> str:
    """Address players on the local network use to join (``ip:port``)."""
    host = server.config.address
    if not host or host in ("0.0.0.0", "::"):
        host = local_ip_address() or "localhost"
    return f"{host}:{server.config.port}"
