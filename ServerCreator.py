"""Main"""
import os
from nicegui import ui, html, app

from modules.pages import (
    build_base_window,
    home,
)


class Main:
    """Main class"""
    def __init__(self):
        app.add_static_files(
            "/static",
            os.path.join(os.getcwd(), "static")
        )

    def run(self):
        """Main"""
        build_base_window()
        container = html.section()
        home(container)

        ui.run(
            native=True,
            window_size=(1300, 800),
            reload=False,
            title="Minecraft Server Creator",
            dark=True,
            frameless=True
        )

Main().run()
