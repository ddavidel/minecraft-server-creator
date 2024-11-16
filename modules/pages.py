"""
Pages
"""

from nicegui import ui, html, app

from modules.utils import popup_create_server


def build_base_window():
    """Builds base window for app"""
    ui.add_head_html("<link rel='stylesheet' href='/static/style.css'>")
    with ui.row().style("position: absolute; top: 10px; right: 10px;"):
        ui.button("", on_click=app.shutdown, icon="close").classes("close-button")

    with ui.left_drawer(top_corner=True, fixed=True).classes("left-drawer"):
        ui.label("MCS").style("font-size: 2rem;")
        ui.button(
            "Create Server", on_click=popup_create_server().open, icon="add_circle",
        ).classes("drawer-button")
        ui.button(
            "Dashboard", on_click=None, icon="space_dashboard",
        ).classes("drawer-button")
        ui.button(
            "Console", on_click=None, icon="terminal",
        ).classes("drawer-button")


def home(container):
    """Home page"""
    with container.classes("content"):
        ui.label("Minecraft Server Creator").style("font-size: 40px;")
        ui.label("insert simple server list here.")

        with ui.row(align_items="center").style("width: 100%"):
            ui.skeleton().classes("server-card")
            ui.skeleton().classes("server-card")
            ui.skeleton().classes("server-card")
            ui.skeleton().classes("server-card")
