"""
Bridge between the GUI and the pymcsc library (imported as ``mcsc``).

pymcsc owns everything about servers (registry, install, process, monitoring,
config files). This module adds what the library deliberately leaves to the app:
the shared ``ServerManager`` instance, telemetry, translated labels and errors,
and UI notifications.
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import ui

from mcsc import (
    DownloadError,
    EulaNotAcceptedError,
    InstallError,
    JavaNotFoundError,
    MCSCError,
    MinecraftServer,
    ServerConfig,
    ServerManager,
    ServerNotFoundError,
    ServerNotRunningError,
    ServerRunningError,
    ServerState,
    ServerType,
    UnsupportedVersionError,
    VersionNotFoundError,
)

from mcsc_gui.config import settings as mcssettings
from mcsc_gui.modules.translations import translate as _
from mcsc_gui.telemetry import send_event_async

logger = logging.getLogger(__name__)

manager = ServerManager(
    mcssettings.SERVER_DIR_PATH,
    mcssettings.SERVERS_JSON_PATH,
    output_buffer=mcssettings.MAX_LOG_LINES,
)

# Options for the "Server Type" selects: {0: "Vanilla", 1: "Paper", 2: "Forge"}
SERVER_TYPES: dict[int, str] = {int(t): t.label for t in ServerType}

STATE_LABELS: dict[ServerState, str] = {
    ServerState.STOPPED: "Stopped",
    ServerState.STARTING: "Starting",
    ServerState.RUNNING: "Running",
    ServerState.STOPPING: "Stopping",
}

# Most specific first: the first matching type wins.
ERROR_MESSAGES: tuple[tuple[type[MCSCError], str], ...] = (
    (EulaNotAcceptedError, "EULA not accepted"),
    (ServerRunningError, "Can't do this while the server is running"),
    (ServerNotRunningError, "The server is not running"),
    (ServerNotFoundError, "Invalid server"),
    (JavaNotFoundError, "Java not found. Install Java and try again"),
    (UnsupportedVersionError, "Unsupported Forge Version. THIS IS NOT A BUG!"),
    (VersionNotFoundError, "Version URL not found"),
    (DownloadError, "Download failed. Check your internet connection"),
    (InstallError, "Server installation failed"),
)

_attached: set[str] = set()


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


def can_start(server: MinecraftServer) -> bool:
    """True when the start button should be enabled."""
    return not server.is_active


def can_stop(server: MinecraftServer) -> bool:
    """True when the stop button should be enabled."""
    return server.state in (ServerState.STARTING, ServerState.RUNNING)


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
    """Show an error notification in the current UI context."""
    ui.notify(error_message(error), type="negative")


# --------------------------------------------------------------- lifecycle


async def _on_state_change(server: MinecraftServer, old: ServerState, new: ServerState) -> None:
    """Server state listener: sends start/stop telemetry."""
    if new is ServerState.STARTING:
        await send_event_async("server_start", details=telemetry_details(server))
    elif new is ServerState.STOPPED and old is not ServerState.STOPPED:
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


def register_server(config: ServerConfig) -> MinecraftServer:
    """Register an already installed server (used by the legacy migration)."""
    return _attach(manager.register(config))


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
    await send_event_async("server_create", details=telemetry_details(server))
    return server


def update_server(server: MinecraftServer, name: str, ram_gb: int) -> None:
    """Change a server's editable settings and persist them."""
    name = (name or "").strip()
    if not name:
        raise ValueError(_("Server name can't be empty"))
    server.config.name = name
    server.config.ram_gb = int(ram_gb)
    manager.save()


async def delete_server(server: MinecraftServer, delete_files: bool) -> None:
    """Unregister a stopped server, optionally deleting its folder."""
    details = telemetry_details(server)
    manager.delete(server, delete_files=delete_files)
    _attached.discard(server.id)
    await send_event_async("server_delete", details=details)


async def start_server(server: MinecraftServer) -> None:
    """Start a server, notifying the user on failure."""
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
    """Stop every running server."""
    logger.info("Stopping all servers...")
    await manager.stop_all(mcssettings.SERVER_STOP_TIMEOUT)


def config_file_exists(server: MinecraftServer, filename: str) -> bool:
    """True if an editable config file exists in the server folder."""
    try:
        return server.config_file_path(filename).is_file()
    except ValueError:
        return False
