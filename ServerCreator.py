"""Main"""
import os
from nicegui import ui, html, app

from modules.pages import (
    build_base_window,
    build_drawer,
    home,
)
from modules.server import load_servers
from modules.utils import (
    load_server_versions
)


app.native.window_args['resizable'] = False


class Main:
    """Main class"""
    def __init__(self):
        """
        Loads stuff.
        IMPORTANT: Order matters.
        """
        app.add_static_files(
            "/static",
            os.path.join(os.getcwd(), "static")
        )
        ui.colors(primary="#13c187")
        load_servers()
        load_server_versions()

    def run(self):
        """Main"""
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
            frameless=True
        )

Main().run()
