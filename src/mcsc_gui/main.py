"""Application bootstrap and lifecycle for the NiceGUI desktop app."""

from __future__ import annotations

import json
import logging
import shutil
from importlib.metadata import version
from pathlib import Path

from nicegui import app, html, ui

from mcsc import ServerConfig

from mcsc_gui.config import settings as mcssettings
from mcsc_gui.modules.logger import setup_logging
from mcsc_gui.modules.pages import build_base_window, build_drawer, home
from mcsc_gui.modules.server_manager import (
    find_server,
    load_servers,
    preload_versions,
    register_server,
    stop_all_servers,
)
from mcsc_gui.telemetry import get_telemetry_client
from mcsc_gui.utils import static_dir

app.native.window_args["resizable"] = False
logger = logging.getLogger(__name__)


class ServerCreatorGUI:
    """Main desktop application class."""

    DEFAULT_WINDOW_SIZE = (1300, 800)

    def __init__(self) -> None:
        """Initialize the app state and data bootstrap."""
        setup_logging(debug=mcssettings.DEBUG)
        self.telemetry_client = get_telemetry_client()
        load_servers()
        self.migrate_legacy()
        preload_versions()

    @staticmethod
    @ui.page("/")
    def main_page() -> None:
        """Render the home route."""
        header = ui.header().classes("content-header")
        container = html.section()
        build_base_window(header=header)
        build_drawer()
        home(header=header, container=container)

    def initialize_runtime(self) -> None:
        """Register static assets and prepare the app runtime."""
        app.add_static_files("/static", str(static_dir))
        # Never leave orphan server processes behind, however the app is closed
        app.on_shutdown(stop_all_servers)

    def run(self, *, debug: bool = False) -> None:
        """Run the desktop UI using NiceGUI's native mode."""
        self.telemetry_client.send_event(
            event_name="app_start",
            details={"version": version(mcssettings.PACKAGE_NAME)},
        )
        self.initialize_runtime()

        ui.run(
            native=True,
            window_size=self.DEFAULT_WINDOW_SIZE,
            reload=False,
            title="Minecraft Server Creator",
            dark=True,
            frameless=True,
            show=debug,
            reconnect_timeout=60,
        )

    def migrate_legacy(self) -> None:
        """Perform migration from a legacy server config to the current layout."""
        migration_file = Path(mcssettings.DATA_DIR_PATH) / "migration.mgr"
        if not migration_file.exists():
            return

        logger.info("Detected servers migration for legacy version of MCSC")
        legacy_servers_json = migration_file.read_text(encoding="utf-8").strip()
        legacy_servers_dict = json.loads(Path(legacy_servers_json).read_text(encoding="utf-8"))

        for server_uuid, legacy_config in legacy_servers_dict.items():
            logger.info(f"Migrating server '{server_uuid}' ({legacy_config.get('name')})...")
            new_server_folder = Path(mcssettings.SERVER_DIR_PATH) / server_uuid

            if new_server_folder.exists() or find_server(server_uuid) is not None:
                continue

            shutil.copytree(legacy_config["folder_path"], new_server_folder)

            # ServerConfig.from_dict understands the legacy keys (jar_type, dedicated_ram, ...)
            config = ServerConfig.from_dict({**legacy_config, "uuid": server_uuid})
            config.path = new_server_folder
            register_server(config)

        migration_file.rename(migration_file.with_suffix(".mgr.done"))
        logger.info("Migration completed successfully.")


def main() -> None:
    """Module-level entry point for the application."""
    ServerCreatorGUI().run()
