"""
Pages
"""

from nicegui import ui, app

from modules.utils import popup_create_server, create_server_card
from modules.server import server_list


def build_base_window(header: ui.header):
    """Builds base window for app"""
    ui.add_head_html("<link rel='stylesheet' href='/static/style.css'>")
    # TODO: add here other css files.
    with header:
        ui.button("", on_click=app.shutdown, icon="close").classes("close-button")

    with ui.left_drawer(top_corner=True, fixed=True).classes("left-drawer"):
        ui.label("MCS").style("font-size: 2rem;")
        ui.button(
            "Create Server",
            on_click=popup_create_server().open,
            icon="add_circle",
        ).classes("drawer-button drawer-button-primary")
        ui.button(
            "Dashboard",
            on_click=None,
            icon="space_dashboard",
        ).classes("drawer-button")
        ui.button(
            "Console",
            on_click=None,
            icon="terminal",
        ).classes("drawer-button")


def home(header: ui.header, container):
    """Home page"""
    with header:
        ui.label("Your servers").style("font-size: 40px;")

    with container.classes("content"):
        with ui.row(align_items="center").style("width: 100%"):
            if server_list:
                for server in server_list:
                    create_server_card(server=server)
            else:
                container.classes("content content-empty-state")
                with ui.row().classes("center-text-horizontal").style(
                    "margin-left: 47% !important;"
                ):
                    ui.icon("splitscreen").style("font-size: 80px;")
                with ui.row().classes("center-text-horizontal"):
                    ui.label("Seems like you don't have any. Let's create one!")
