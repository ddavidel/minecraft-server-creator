"""
Utils
"""

import io
import asyncio
import psutil
from nicegui import ui
import requests
import pandas as pd
from modules.server import MinecraftServer


VERSION_LIST_URL = "https://gist.githubusercontent.com/cliffano/77a982a7503669c3e1acb0a0cf6127e9/raw/a36b1e2f05ed3f1d1bbe9a7cf7fd3cfc7cb7a3a8/minecraft-server-jar-downloads.md"


server_versions = []
server_types = {
    0: "Vanilla",
    1: "Spigot",
    2: "Forge",
}
vanilla_urls = {}
spigot_urls = {}

urls = None  # pylint: disable=invalid-name


def _get_system_total_ram():
    """Total ram on device in GB"""
    return round(psutil.virtual_memory().total / (1024**3))


def popup_create_server():
    """Create server popup window"""
    # local variables
    system_ram = _get_system_total_ram()
    server_settings = {
        "dedicated_ram": 0,
        "version": "",
        "jar_type": 0,
        "address": "",
        "port": 25565,
    }

    async def _create_server(server_name: str, server_settings: dict):
        n = ui.notification(timeout=None)
        n.message = "Creating server"
        n.spinner = True
        await asyncio.sleep(1)
        server_instance = MinecraftServer(name=server_name, settings=server_settings)
        # what else to do here?
        n.message = "Server created!"
        n.spinner = False
        await asyncio.sleep(3)
        n.dismiss()

    with ui.dialog() as popup, ui.card().classes("create-server-popup"):
        with ui.row():
            ui.label("New Server").style("font-size: 30px;")

        with ui.row().style("width: 100%;"):
            name_input = ui.input(
                label="Server name",
                validation={"Too long!": lambda value: len(value) < 35},
            ).classes("create-server-input")
            ui.input(
                label="IPv4 Address",
                validation={"Too long!": lambda value: len(value) < 16},
            ).classes("create-server-input").bind_value_to(
                server_settings,
                "address",
            )

        ui.separator()

        ui.label("Dedicated RAM").style("font-size: 30px;")
        ui.label(f"Suggested: {round(system_ram/4)}GB")
        with ui.row().style("width: 100%; margin-top: 10px;"):
            ui.slider(
                max=system_ram,
                min=1,
                step=1,
                value=round(system_ram / 4),
            ).classes("create-server-input").style("width: 100%;").props(
                "label-always"
            ).bind_value_to(
                server_settings, "dedicated_ram"
            )

        ui.separator()
        ui.label("Other settings").style("font-size: 30px;")

        with ui.row().style("width: 100%;"):
            ui.select(server_types, with_input=True, label="Server Type").bind_value_to(
                server_settings, "jar_type"
            ).classes("create-server-input")
            ui.select(server_versions, with_input=True, label="Server Version").classes(
                "create-server-input"
            ).bind_value_to(server_settings, "version")

        with ui.row().style("width: 100%;").style("flex-grow: 1;"):
            ui.button("Cancel", on_click=popup.close)
            ui.button(
                "Create",
                on_click=lambda x: _create_server(
                    server_name=name_input.value, server_settings=server_settings
                ),
            )
        return popup


def create_server_card(server: MinecraftServer):
    """Create a server card for server"""
    with ui.card().classes("server-card"):
        with ui.row():
            ui.label(server.name).style("font-size: 25px")
        with ui.row():
            with ui.button_group():
                ui.button(icon="play_arrow").on_click(server.start).classes(
                    "start-button"
                ).bind_enabled_from(server, "running", lambda s: not s)

                ui.button(icon="stop").on_click(server.stop).classes(
                    "stop-button"
                ).bind_enabled_from(server, "running")

            ui.label(f"Status: {server.status}").style(
                "opacity: 0.6; margin-left: 200px; margin-top: 10px;"
            )


def load_server_versions():
    """Loads server versions"""
    response = requests.get(VERSION_LIST_URL, timeout=10)
    response.raise_for_status()
    markdown_content = response.text
    # Use pandas to read the Markdown table
    df = pd.read_csv(
        io.StringIO(markdown_content),
        sep="|",
        skipinitialspace=True,
        skiprows=0,
        engine="python",
    )

    df.columns = [col.strip() for col in df.columns]

    df = df.drop(
        columns=["Unnamed: 0", "Unnamed: 4", "Client Jar Download URL"], errors="ignore"
    )
    df = df.drop(index=0)
    df["Minecraft Version"] = df["Minecraft Version"].str.strip()
    df["Server Jar Download URL"] = df["Server Jar Download URL"].str.strip()
    df.index = df["Minecraft Version"].str.strip()
    del df["Minecraft Version"]

    vanilla_dict = dict(zip(df.index, df["Server Jar Download URL"]))
    global server_versions, urls  # pylint:disable=global-statement
    urls = JarUrl()
    urls.set_urls(jar_type=0, data_dict=vanilla_dict)


class JarUrl:
    """Utility class"""

    def __init__(self):
        self.vanilla_urls = {}
        self.spigot_urls = {}
        self.forge_urls = {}

    def set_urls(self, jar_type: int, data_dict: dict):
        """sets vanilla urls"""
        if jar_type == 0:
            self.vanilla_urls = data_dict.copy()
        elif jar_type == 1:
            self.spigot_urls = data_dict.copy()
        elif jar_type == 2:
            self.forge_urls = data_dict.copy()
        self.update_version_list()

    def get_url(self, version: str, jar_type: int) -> str:
        """returns url of version"""
        if jar_type == 0:
            # vanilla url
            if not self.vanilla_urls.get(version):
                raise ValueError("Version url not found")
            return self.vanilla_urls.get(version)

    def update_version_list(self):
        """updates server versions list"""
        global server_versions  # pylint:disable=global-statement
        version_list = (
            list(self.vanilla_urls.keys())
            + list(self.spigot_urls.keys())
            + list(self.forge_urls.keys())
        )
        server_versions = list(set(version_list))
