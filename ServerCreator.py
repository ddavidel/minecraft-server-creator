"""Main"""
import os
from nicegui import ui, html, app


class Main:
    """Main class"""
    def __init__(self):
        app.add_static_files(
            "/static",
            os.path.join(os.getcwd(), "static")
        )

    def run(self):
        """Main"""
        ui.add_head_html("<link rel='stylesheet' href='/static/style.css'>")

        with ui.header(elevated=True).classes("nav-bar"):
            ui.label("Minecraft Server Creator")

        with html.section().classes("content"):
            ui.label("Minecraft Server Creator").style("font-size: 40px; ")

        ui.run(
            native=True,
            window_size=(800, 600),
            reload=False,
            title="Minecraft Server Creator",
        )

Main().run()
