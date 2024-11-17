"""
Utils
"""

import psutil
import asyncio
from nicegui import ui
from modules.server import MinecraftServer

mc_versions = [
    "1.8.9",
    "1.12.2",
    "1.20.2",  # random ver
]
server_types = {
    0: "Vanilla",
    1: "Spigot",
    2: "Forge",
}


def _get_system_total_ram():
    """Total ram on device in GB"""
    return round(psutil.virtual_memory().total / (1024**3))


def popup_create_server():
    """Create server popup window"""

    def _update_ram_slider(value: int | float, label: ui.label):
        t1 = f"RAM: {value}/{_get_system_total_ram()}GB."
        t2 = f"Suggested: {round(_get_system_total_ram()/4)}GB"
        label.text = f"{t1} {t2}"

    async def _create_server():
        n = ui.notification(timeout=None)
        for i in range(10):
            n.message = f"Computing {i/10:.0%}"
            n.spinner = True
            await asyncio.sleep(0.2)
        n.message = "Done!"
        n.spinner = False
        await asyncio.sleep(1)
        n.dismiss()

    with ui.dialog() as popup, ui.card().classes("create-server-popup"):
        with ui.row():
            ui.label("New Server").style("font-size: 30px;")

        ui.input(label="Server name", validation={'Too long!': lambda value: len(value) < 35})
        ram_label = ui.label(
            f"RAM: 1/{_get_system_total_ram()}GB. "
            f"Suggested: {round(_get_system_total_ram()/4)}GB"
        )
        ui.slider(
            max=_get_system_total_ram(),
            min=1,
            step=1,
            value=1,
            on_change=lambda e: _update_ram_slider(e.value, ram_label),
        )

        ui.separator()

        with ui.row():
            ui.select(server_types, with_input=True, label="Server Type")
            ui.select(mc_versions, with_input=True, label="Server Version")

        with ui.row():
            ui.button("Cancel", on_click=popup.close)
            ui.button("Create", on_click=_create_server)
        return popup


def create_server_card(server: MinecraftServer):
    """Create a server card for server"""
    with ui.card().classes("server-card"):
        with ui.row():
            ui.label(server.name).style("font-size: 25px")
        with ui.row():
            start_btn = ui.button(icon="play_arrow").classes("start-button")
            stop_btm = ui.button(icon="stop").classes("stop-button")
            if server.running:
                start_btn.disable()
            else:
                stop_btm.disable()

            ui.label(f"Status: {server.status}").style(
                "opacity: 0.6; margin-left: 190px; margin-top: 10px;"
            )
