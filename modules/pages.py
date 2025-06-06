"""
Pages
"""

import asyncio
from nicegui import ui, html

from config import settings as mcssettings

from modules.utils import (
    popup_create_server,
    popup_edit_server,
    write_to_console_and_clean,
    popup_delete_server,
    shutdown,
    popup_update_app,
    popup_app_settings,
    open_file_explorer,
    minimize_window,
)
from modules.servers.models import MinecraftServer, get_server_list
from modules.servers.paper import PaperServer
from modules.servers.utils import get_server_by_uuid, FILE_TO_ATTR
from modules.translations import translate as _
from modules.logger import RotatingLogger
from update import check_for_updates

update_available = check_for_updates()
logger = RotatingLogger()


def load_head():
    """Loads page head"""
    # add here other css files.
    ui.add_head_html("<link rel='stylesheet' href='/static/style.css'>")
    ui.colors(primary="#13c187")


def build_base_window(header: ui.header):
    """Builds base window for app"""
    load_head()
    with header:
        ui.button("", on_click=minimize_window, icon="remove").classes("minimize-button")
        ui.button("", on_click=shutdown, icon="close").classes("close-button")


def build_drawer():
    """Builds left drawer"""
    # Setup
    update_popup = popup_update_app()

    async def _check_updates(update_btn: ui.button):
        update_btn.disable()
        global update_available  # pylint: disable=global-statement

        if not update_available:
            notification = ui.notification(
                message=_("Checking for updates..."),
                timeout=3,
                spinner=True,
                type="info",
            )
            await asyncio.sleep(1)

            if check_for_updates():
                update_available = True
                update_btn.style("background-color: rgb(255, 152, 0) !important")
                notification.message = _("Update available")
                notification.spinner = False
                update_btn.set_text(_("Update available"))
                update_popup.open()
            else:
                update_available = False
                notification.message = _("No updates available")
                notification.spinner = False

        else:
            update_popup.open()

        update_btn.enable()

    # Build drawer
    with ui.left_drawer(top_corner=True, fixed=True).classes("left-drawer"):
        # Logo
        ui.image("/static/logo.png")

        # App Buttons
        ui.button(
            _("Create Server"),
            on_click=popup_create_server().open,
            icon="add_circle",
        ).classes("drawer-button drawer-button-primary")
        ui.button(
            _("Dashboard"),
            on_click=home.refresh,
            icon="space_dashboard",
        ).classes("drawer-button")

        # Split the buttons
        ui.space()

        # with ui.expansion(_("Settings"), icon="settings").style(
        #     "width: 100%; border-radius: 10px;"
        # ):
        # Update
        update_button = ui.button(
            _("Check for updates"),
            on_click=lambda x: _check_updates(x.sender),
            icon="download",
        ).classes("drawer-button")

        # Automatically check for updates (this could be a user setting)
        if update_available:
            update_button.style("background-color: rgb(255, 152, 0) !important")
            update_button.set_text(_("Update available"))
            update_popup.open()
            ui.notification(
                message=_("Update available"),
                timeout=30,
                spinner=False,
                type="info",
            )

        # Settings
        ui.button(
            _("App Settings"),
            on_click=popup_app_settings().open,
            icon="tune",
        ).classes("drawer-button")


@ui.page("/server_detail/{uuid}")
def server_detail(uuid: str):
    """Page that displays the server details"""
    logger.info(f"GET /server_detail/{uuid}")
    # setup content
    load_head()
    header = ui.header().classes("content-header")
    container = html.section().classes("content")

    server = get_server_by_uuid(uuid=uuid)

    build_base_window(header=header)

    with header:
        with ui.button(
            "", on_click=ui.navigate.back, icon="arrow_back_ios_new"
        ).classes("back-button"):
            ui.tooltip(_("Back")).style("font-size: 15px;").props("delay=1500")
        with ui.label(server.name).style("font-size: 40px;"):
            ui.tooltip(server.uuid).style("font-size: 15px;")
        with ui.button("", icon="folder").style("margin-left: 10px;").on_click(
            lambda x: open_file_explorer(server.server_path)
        ).classes("circular-button"):
            ui.tooltip(_("Open server folder")).style("font-size: 15px;")
        with ui.button_group().style("margin-top: 15px"):
            ui.button(_("Start"), icon="play_arrow").on_click(server.start).classes(
                "start-button"
            ).bind_enabled_from(server, "running", lambda s: not s)

            ui.button(icon="stop").on_click(server.stop).classes(
                "stop-button"
            ).bind_enabled_from(server, "running")

    with ui.left_drawer(top_corner=True, fixed=True).classes("left-drawer"):
        ui.label(_("Settings")).style("font-size: 35px")
        ui.button(
            _("Console"),
            on_click=None,
            icon="terminal",
        ).classes("drawer-button")
        ui.button(
            _("Edit server settings"),
            on_click=popup_edit_server(server=server).open,
            icon="tune",
        ).classes("drawer-button")
        ui.button(
            _("Edit server properties"),
            on_click=lambda x: ui.navigate.to(f"/edit/{server.uuid}/server.properties"),
            icon="edit_note",
        ).classes("drawer-button").bind_enabled_from(
            server,
            "has_server_properties",
        )
        if isinstance(server, PaperServer):
            ui.button(
                _("Edit spigot properties"),
                on_click=lambda x: ui.navigate.to(f"/edit/{server.uuid}/spigot.yml"),
                icon="edit_note",
            ).classes("drawer-button").bind_enabled_from(
                server,
                "has_spigot_yml",
            )
            ui.button(
                _("Edit paper properties"),
                on_click=lambda x: ui.navigate.to(f"/edit/{server.uuid}/paper.yml"),
                icon="edit_note",
            ).classes("drawer-button").bind_enabled_from(
                server,
                "has_paper_yml",
            )
        ui.button(
            _("Delete server"),
            on_click=lambda x: popup_delete_server(server=server),
            icon="delete",
        ).classes("drawer-button").style(
            "background-color: rgb(216, 68, 68) !important"
        )

        # Stats section
        ui.space()
        # ui.label(_("System Usage")).style("font-size: 25px opacity: 0.6;")
        ui.separator()
        with ui.grid(rows=2, columns=2).classes("stat-grid"):
            # RAM usage
            with ui.chip("", icon="donut_large").bind_text_from(
                server.monitor, "ram_usage", lambda x: f"{x} MB"
            ).classes("stat-chip"):
                ui.tooltip(_("RAM usage")).style("font-size: 15px;")
            # CPU usage
            with ui.chip("", icon="memory").bind_text_from(
                server.monitor, "cpu_usage", lambda x: f"{x} %"
            ).classes("stat-chip"):
                ui.tooltip(_("CPU usage")).style("font-size: 15px;")
            # Disk read
            with ui.chip("", icon="swap_vert").bind_text_from(
                server.monitor,
                "disk_read",
                lambda x: f"{x} MB/s",
            ).classes("stat-chip"):
                ui.tooltip(_("Disk read")).style("font-size: 15px;")
            # Disk write
            with ui.chip("", icon="swap_vert").bind_text_from(
                server.monitor,
                "disk_write",
                lambda x: f"{x} MB/s",
            ).classes("stat-chip"):
                ui.tooltip(_("Disk write")).style("font-size: 15px;")

    with container:
        log = ui.log(mcssettings.MAX_LOG_LINES).classes("log-window")
        server.log = log

        with ui.row().style("width: 100%;"):
            console_input = (
                ui.input(_("Write command"))
                .on(
                    "keydown.enter",
                    handler=lambda x: write_to_console_and_clean(
                        caller=console_input, server=server
                    ),
                )
                .classes("console-input")
            )


def create_server_card(server: MinecraftServer):
    """Create a server card for server"""
    with ui.card().classes("server-card"):
        with ui.row():
            ui.link(server.name, f"/server_detail/{server.uuid}").classes(
                "server-card-link"
            )

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
                server,
                "status",
                backward=lambda value: _("Status: {value}", value=value),
            )


@ui.refreshable
def home(header: ui.header, container):
    """Home page"""
    logger.info("GET /home")
    # clear content before
    container.clear()
    header.clear()
    build_base_window(header=header)
    server_list = get_server_list()

    with header:
        ui.label(_("Your servers")).style("font-size: 40px;")
        ui.button("", icon="refresh", on_click=home.refresh).classes("refresh-button")

    with container.classes("content"):
        with ui.row(align_items="center").style("width: 100%"):
            if server_list:
                if "content-empty-state" in container.classes:
                    container.classes.remove("content-empty-state")
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
                    ui.label(_("Seems like you don't have any. Let's create one!"))


@ui.page("/edit/{uuid}/{what}")
def edit_server_properties(uuid: str, what: str = "server.properties"):
    """
    A page that displays to the user a text editor to edit
    the a file.
    This can be server.properties or spigot.yml
    """
    logger.info(f"GET /edit/{uuid}")
    # setup content
    load_head()
    header = ui.header().classes("content-header")
    container = html.section().classes("content")

    server = get_server_by_uuid(uuid=uuid)

    if what == "server.properties":
        server.load_server_properties()
    elif what in ("spigot.yml", "paper.yml") and isinstance(server, PaperServer):
        if what == "spigot.yml":
            server.load_spigot_yml()
        elif what == "paper.yml":
            server.load_paper_yml()
        else:
            logger.error(f"Unknown file {what} for server {server.uuid}")
            raise ValueError(f"Unknown file {what} for server {server.uuid}")

    data = getattr(server, FILE_TO_ATTR[what])

    async def _saving(server: MinecraftServer, editor: ui.editor):
        await asyncio.sleep(0.5)
        try:
            if what in ("spigot.yml", "paper.yml"):
                saved = server.save_yml(filename=what, editor=editor)
            else:
                saved = server.save_server_properties(editor=editor)

            if saved:
                n = ui.notification(message="Saved", spinner=False, type="positive")
                await asyncio.sleep(3)
                n.dismiss()

        except Exception as e:
            n = ui.notification(
                message=str(e),
                type="negative",
                spinner=False,
            )
            await asyncio.sleep(3)
            n.dismiss()

    with header.style("background-color: rgba(18, 18, 18, 0.75)"):
        ui.button("", on_click=shutdown, icon="close").classes("close-button")
        ui.button("", on_click=ui.navigate.back, icon="arrow_back_ios_new").classes(
            "back-button"
        )
        ui.label(server.name).style("font-size: 40px;")

    with container:
        ui.json_editor({"content": {"json": data}}).classes(
            "properties-editor"
        ).on_change(lambda editor: _saving(server=server, editor=editor))
