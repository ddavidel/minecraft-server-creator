"""Main"""

import os
from nicegui import ui, html, app

from modules.pages import (
    build_base_window,
    build_drawer,
    home,
)
from modules.servers.utils import load_servers
from modules.utils import load_server_versions
from modules.telemetry import TelemetryClient
from appdirs import user_data_dir


app.native.window_args["resizable"] = False


class Main:
    """Main class"""

    def __init__(self):
        """
        Loads stuff.
        IMPORTANT: Order matters.
        """
        self.telemetry_client = TelemetryClient()
        app.add_static_files("/static", os.path.join(os.getcwd(), "static"))
        load_servers()
        load_server_versions()

        # V2 migration
        app_data_dir = user_data_dir("mcsc")
        # create .mgr file in app data dir. The file contains the path of the
        # config/servers.json file
        mgr_file_path = os.path.join(app_data_dir, "migration.mgr")
        os.makedirs(app_data_dir, exist_ok=True)
        with open(mgr_file_path, "w", encoding="utf-8") as mgr_file:
            servers_config_path = os.path.join(
                os.getcwd(), "config", "servers.json"
            )
            mgr_file.write(servers_config_path)
            mgr_file.flush()


    def run(self):
        """Main"""
        self.telemetry_client.send_event(event_name="app_start")
        # Prepare components
        header = ui.header().classes("content-header")
        container = html.section()

        # Build view
        build_base_window(header=header)
        build_drawer()
        home(header=header, container=container)

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


if __name__ == "__main__":
    Main().run()
