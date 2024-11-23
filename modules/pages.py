"""
Pages
"""

from nicegui import ui, html, app

from config import settings as mcssettings

from modules.utils import (
    popup_create_server,
    popup_edit_server
)
from modules.server import (
    MinecraftServer,
    server_list,
    get_server_by_uuid
)


def load_head():
    """Loads page head"""
    # add here other css files.
    ui.add_head_html("<link rel='stylesheet' href='/static/style.css'>")
    ui.colors(primary="#13c187")


def build_base_window(header: ui.header):
    """Builds base window for app"""
    load_head()
    with header:
        ui.button("", on_click=app.shutdown, icon="close").classes("close-button")

def build_drawer():
    """Builds left drawer"""
    with ui.left_drawer(top_corner=True, fixed=True).classes("left-drawer"):
        ui.label("MCServerCreator").style("font-size: 35px")
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

@ui.page('/server_detail/{uuid}')
def server_detail(uuid: str):
    """Page that displays the server details"""
    # setup content
    load_head()
    header = ui.header().classes("content-header")
    container = html.section().classes("content")

    server = get_server_by_uuid(uuid=uuid)

    with header:
        ui.button("", on_click=app.shutdown, icon="close").classes("close-button")
        ui.button("", on_click=ui.navigate.back, icon="arrow_back_ios_new").classes(
            "back-button"
        )
        ui.label(server.name).style("font-size: 40px;")
        # TODO: use this chip to display server status
        ui.chip(color='green').bind_value_from(
            server,
            "status"
        )

    with ui.left_drawer(top_corner=True, fixed=True).classes("left-drawer"):
        ui.label("Settings").style("font-size: 35px")
        ui.button(
            "Console",
            on_click=None,
            icon="terminal",
        ).classes("drawer-button")
        ui.button(
            "Edit server settings",
            on_click=popup_edit_server(server=server).open,
            icon="tune",
        ).classes("drawer-button")
        ui.button(
            "Edit server properties",
            on_click=None,
            icon="edit_note",
        ).classes("drawer-button").bind_enabled_from(
            server,
            "has_server_properties",
        )

    with container:
        log = ui.log(mcssettings.MAX_LOG_LINES).classes("log-window")
        server.log = log

def create_server_card(server: MinecraftServer):
    """Create a server card for server"""
    with ui.card().classes("server-card"):
        with ui.row():
            ui.link(server.name, f"/server_detail/{server.uuid}").classes("server-card-link")

        with ui.row():
            with ui.button_group():
                ui.button(icon="play_arrow").on_click(server.start).classes(
                    "start-button"
                ).bind_enabled_from(server, "running", lambda s: not s)

                ui.button(icon="stop").on_click(server.stop).classes(
                    "stop-button"
                ).bind_enabled_from(server, "running")

            ui.label("").style(
                "opacity: 0.6; margin-left: 200px; margin-top: 10px;"
            ).bind_text_from(
                server, "status", backward=lambda value: f"Status: {value}"
            )


@ui.refreshable
def home(header: ui.header, container):
    """Home page"""
    # clear content before
    container.clear()
    header.clear()
    build_base_window(header=header)

    with header:
        ui.label("Your servers").style("font-size: 40px;")
        ui.button("", icon="refresh", on_click=home.refresh).classes("refresh-button")

    with container.classes("content"):
        with ui.row(align_items="center").style("width: 100%"):
            if server_list:
                container.classes("content")
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
