"""Main"""

import json
import shutil
from pathlib import Path
from importlib.metadata import version
from nicegui import ui, html, app

from mcsc.modules.pages import (
    build_base_window,
    build_drawer,
    home,
)
from mcsc.modules.servers.utils import load_servers, TYPE_TO_CLASS
from mcsc.modules.utils import load_server_versions
from mcsc.utils import static_dir
from mcsc.telemetry import TelemetryClient
from mcsc.config.settings import DATA_DIR_PATH, SERVER_DIR_PATH, PACKAGE_NAME


app.native.window_args["resizable"] = False


class ServerCreatorGUI:
    """Main class"""

    def __init__(self):
        """
        Loads stuff.
        IMPORTANT: Order matters.
        """
        self.telemetry_client = TelemetryClient()
        # app.add_static_files("/static", str(static_dir))
        # Load server (creates servers.json file if not found)
        load_servers()
        load_server_versions()
        self.migrate_legacy()

    @staticmethod
    @ui.page("/")
    def main_page():
        # Prepare components
        # app.add_static_files("/static", str(static_dir))
        header = ui.header().classes("content-header")
        container = html.section()

        # Build view
        build_base_window(header=header)
        build_drawer()
        home(header=header, container=container)

    def run(self):
        """Main"""
        # self.telemetry_client.send_event(event_name="app_start")
        # # Prepare components
        # header = ui.header().classes("content-header")
        # container = html.section()

        # # Build view
        # build_base_window(header=header)
        # build_drawer()
        # home(header=header, container=container)
        self.telemetry_client.send_event(
            event_name="app_start", details={"version": version(PACKAGE_NAME)}
        )
        app.add_static_files("/static", str(static_dir))

        ui.run(
            native=True,
            window_size=(1300, 800),
            reload=False,
            title="Minecraft Server Creator",
            dark=True,
            frameless=True,
            show=False,
            reconnect_timeout=60,
        )

    def migrate_legacy(self):
        """Perform migration from legacy to new version"""
        # pylint: disable=unspecified-encoding
        # Check if there is a migration file: 'migration.mgr' in data dir
        migration_file = Path(DATA_DIR_PATH) / "migration.mgr"

        if migration_file.exists():
            # Perform migration

            print("Detected servers migration for legacy version of MCSC")
            legacy_servers_json: str = migration_file.read_text().strip()
            legacy_servers_dict: dict = json.loads(
                Path(legacy_servers_json).read_text()
            )

            for server_uuid, config in legacy_servers_dict.items():
                print(f"Migrating server '{server_uuid}' ({config['name']})...")

                server_folder = config["folder_path"]

                # Copy server folder into SERVER_DIR_PATH
                new_server_folder: Path = Path(SERVER_DIR_PATH) / server_uuid
                if not new_server_folder.exists():
                    shutil.copytree(server_folder, new_server_folder)
                else:
                    # This could happen if the user starts the legacy version
                    # after completing the migration.
                    continue

                # Update server config path
                config["folder_path"] = str(new_server_folder)

                # Saving the migrated server in the servers.json file
                # instance = MinecraftServer(settings=config, uuid=server_uuid)
                instance = TYPE_TO_CLASS[config["jar_type"]](
                    settings=config, uuid=server_uuid
                )
                instance.save()

            # Rename migration file to 'migration.mgr.done'
            migration_file.rename(migration_file.with_suffix(".mgr.done"))
            print("Migration completed successfully.")
