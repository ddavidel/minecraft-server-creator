"""
Pages
"""

from nicegui import ui, html

from modules.utils import close_app, popup_create_server


def build_base_window():
    """Builds base window for app"""
    ui.add_head_html("<link rel='stylesheet' href='/static/style.css'>")
    with ui.row().style("position: absolute; top: 10px; right: 10px;"):
        ui.button("", on_click=close_app, icon="close").classes("close-button")

    with ui.left_drawer(top_corner=True, fixed=True).classes("left-drawer"):
        ui.label("MCS").style("font-size: 2rem;")
        ui.button(
            "Create Server", on_click=popup_create_server().open, icon="add_circle"
        ).classes("drawer-button")


def home(container):
    """Home page"""
    with container.classes("content"):
        ui.label("Minecraft Server Creator").style("font-size: 40px;")
