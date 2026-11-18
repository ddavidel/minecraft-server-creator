"""
Pages
"""

import asyncio
import json
import logging

from nicegui import ui, html

from mcsc import MinecraftServer, MCSCError

from mcsc_gui.config import settings as mcssettings
from mcsc_gui.modules.server_manager import (
    can_start,
    can_stop,
    config_file_exists,
    error_message,
    find_server,
    get_servers,
    start_server,
    status_label,
    stop_server,
)
from mcsc_gui.modules.utils import (
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
from mcsc_gui.modules.translations import translate as _
from mcsc_gui.update import check_for_updates

# Why is this used here? Because we check for updates while initializing mcsc
# so as soon as the user loads the page it sees the update notification.
# Without this we would have to check every time the user loads the page.
update_available = check_for_updates()
logger = logging.getLogger(__name__)

# Labels of the editor buttons for well known config files
CONFIG_FILE_LABELS = {
    "server.properties": "Edit server properties",
    "spigot.yml": "Edit spigot properties",
    "paper.yml": "Edit paper properties",
    "config/paper-global.yml": "Edit paper properties",
    "bukkit.yml": "Edit bukkit properties",
    "config/paper-world-defaults.yml": "Edit paper world defaults",
}


def load_head():
    """Loads page head."""
    ui.add_head_html("<link rel='stylesheet' href='/static/style.css'>")
    ui.colors(primary="#13c187")


def build_base_window(header: ui.header):
    """Build the common app window chrome."""
    load_head()
    with header:
        ui.button("", on_click=minimize_window, icon="remove").classes("minimize-button")
        ui.button("", on_click=shutdown, icon="close").classes("close-button")


def build_server_controls(server: MinecraftServer) -> None:
    """Start/stop buttons bound to the server state."""
    ui.button(icon="play_arrow").on_click(lambda: start_server(server)).classes(
        "start-button"
    ).bind_enabled_from(server, "state", backward=lambda _s: can_start(server))

    ui.button(icon="stop").on_click(lambda: stop_server(server)).classes(
        "stop-button"
    ).bind_enabled_from(server, "state", backward=lambda _s: can_stop(server))


def build_server_stats(server: MinecraftServer) -> None:
    """Build the server resource summary cards."""
    with ui.grid(rows=2, columns=2).classes("stat-grid"):
        with ui.chip("", icon="donut_large").bind_text_from(
            server.monitor, "usage", lambda u: f"{u.ram_mb} MB"
        ).classes("stat-chip"):
            ui.tooltip(_("RAM usage")).style("font-size: 15px;")

        with ui.chip("", icon="memory").bind_text_from(
            server.monitor, "usage", lambda u: f"{u.cpu_percent} %"
        ).classes("stat-chip"):
            ui.tooltip(_("CPU usage")).style("font-size: 15px;")

        with ui.chip("", icon="swap_vert").bind_text_from(
            server.monitor, "usage", lambda u: f"{u.disk_read_mb} MB/s"
        ).classes("stat-chip"):
            ui.tooltip(_("Disk read")).style("font-size: 15px;")

        with ui.chip("", icon="swap_vert").bind_text_from(
            server.monitor, "usage", lambda u: f"{u.disk_write_mb} MB/s"
        ).classes("stat-chip"):
            ui.tooltip(_("Disk write")).style("font-size: 15px;")


def build_console(server: MinecraftServer) -> None:
    """Console log + command input, fed by the server's output listener."""
    log = ui.log(mcssettings.MAX_LOG_LINES).classes("log-window")
    for line in server.output:
        log.push(line)

    def _push(_server: MinecraftServer, line: str) -> None:
        log.push(line)

    server.add_output_listener(_push)

    def _detach() -> None:
        try:
            server.remove_output_listener(_push)
        except ValueError:
            pass

    ui.context.client.on_disconnect(_detach)

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


def build_not_found(header: ui.header, container) -> None:
    """Content shown when a page refers to a server that doesn't exist."""
    with header:
        ui.button("", on_click=lambda: ui.navigate.to("/"), icon="arrow_back_ios_new").classes(
            "back-button"
        )
    with container:
        ui.label(_("Invalid server")).style("font-size: 30px;")


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
            on_click=popup_create_server(on_created=home.refresh).open,
            icon="add_circle",
        ).classes("drawer-button drawer-button-primary")
        ui.button(
            _("Dashboard"),
            on_click=home.refresh,
            icon="space_dashboard",
        ).classes("drawer-button")

        # Split the buttons
        ui.space()

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

    build_base_window(header=header)

    server = find_server(uuid)
    if server is None:
        build_not_found(header, container)
        return

    with header:
        with ui.button(
            "", on_click=ui.navigate.back, icon="arrow_back_ios_new"
        ).classes("back-button"):
            ui.tooltip(_("Back")).style("font-size: 15px;").props("delay=1500")
        with ui.label().bind_text_from(server.config, "name").style("font-size: 40px;"):
            ui.tooltip(server.id).style("font-size: 15px;")
        with ui.button("", icon="folder").style("margin-left: 10px;").on_click(
            lambda x: open_file_explorer(server.path)
        ).classes("circular-button"):
            ui.tooltip(_("Open server folder")).style("font-size: 15px;")
        with ui.button_group().style("margin-top: 15px"):
            ui.button(_("Start"), icon="play_arrow").on_click(
                lambda: start_server(server)
            ).classes("start-button").bind_enabled_from(
                server, "state", backward=lambda _s: can_start(server)
            )

            ui.button(icon="stop").on_click(lambda: stop_server(server)).classes(
                "stop-button"
            ).bind_enabled_from(server, "state", backward=lambda _s: can_stop(server))

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

        # server.properties is generated on the first start: show it disabled until then.
        # The other config files are shown only if they exist.
        for filename in server.CONFIG_FILES:
            if filename != "server.properties" and not config_file_exists(server, filename):
                continue
            ui.button(
                _(CONFIG_FILE_LABELS.get(filename, "Edit {file}"), file=filename),
                on_click=lambda x, f=filename: ui.navigate.to(f"/edit/{server.id}/{f}"),
                icon="edit_note",
            ).classes("drawer-button").bind_enabled_from(
                server, "state", backward=lambda _s, f=filename: config_file_exists(server, f)
            )

        ui.button(
            _("Delete server"),
            on_click=lambda x: popup_delete_server(server=server).open(),
            icon="delete",
        ).classes("drawer-button").style(
            "background-color: rgb(216, 68, 68) !important"
        )

        ui.space()
        ui.separator()
        build_server_stats(server)

    with container:
        build_console(server)


def create_server_card(server: MinecraftServer):
    """Create a server card for the dashboard."""
    with ui.card().classes("server-card"):
        with ui.row():
            ui.link(server.name, f"/server_detail/{server.id}").classes(
                "server-card-link"
            ).bind_text_from(server.config, "name")

        with ui.row():
            with ui.button_group():
                build_server_controls(server)

            ui.label("").style(
                "opacity: 0.6; margin-left: 200px; margin-top: 10px;"
            ).bind_text_from(
                server,
                "state",
                backward=lambda state: _("Status: {value}", value=status_label(state)),
            )


def render_server_collection(container, server_list):
    """Create the visible server list or empty-state content."""
    if server_list:
        if "content-empty-state" in container.classes:
            container.classes.remove("content-empty-state")
        container.classes("content")
        for server in server_list:
            create_server_card(server=server)
        return

    container.classes("content content-empty-state")
    with ui.row().classes("center-text-horizontal").style(
        "margin-left: 47% !important;"
    ):
        ui.icon("splitscreen").style("font-size: 80px;")
    with ui.row().classes("center-text-horizontal"):
        ui.label(_("Seems like you don't have any. Let's create one!"))


@ui.refreshable
def home(header: ui.header, container):
    """Home page"""
    logger.info("GET /home")
    # clear content before
    container.clear()
    header.clear()
    build_base_window(header=header)
    server_list = get_servers()

    with header:
        ui.label(_("Your servers")).style("font-size: 40px;")
        ui.button("", icon="refresh", on_click=home.refresh).classes("refresh-button")

    with container.classes("content"):
        with ui.row(align_items="center").style("width: 100%"):
            render_server_collection(container, server_list)


def _editor_data(content: dict):
    """Data from a json editor change event (``json`` mode, or ``text`` holding JSON)."""
    if content.get("json") is not None:
        return content["json"]
    text = content.get("text")
    if text:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    return None


@ui.page("/edit/{uuid}/{what:path}")
def edit_server_properties(uuid: str, what: str = "server.properties"):
    """
    A page that displays to the user a text editor to edit a server
    config file (server.properties, spigot.yml, paper.yml...).
    """
    logger.info(f"GET /edit/{uuid}/{what}")
    # setup content
    load_head()
    header = ui.header().classes("content-header")
    container = html.section().classes("content")

    server = find_server(uuid)
    if server is None or what not in server.CONFIG_FILES:
        build_base_window(header=header)
        build_not_found(header, container)
        return

    try:
        data = server.read_config(what)
    except (OSError, ValueError, MCSCError) as e:
        logger.error(f"Can't read {what} for server {server.id}: {e}")
        data = {}
        ui.notify(error_message(e), type="negative")

    async def _saving(content: dict):
        await asyncio.sleep(0.5)
        new_data = _editor_data(content)
        if new_data is None:
            return
        try:
            server.write_config(what, new_data)
            n = ui.notification(message=_("Saved"), spinner=False, type="positive")
            await asyncio.sleep(3)
            n.dismiss()

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(f"Can't save {what} for server {server.id}: {e}")
            n = ui.notification(
                message=error_message(e),
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
        ui.label(f"{server.name} - {what}").style("font-size: 40px;")

    with container:
        ui.json_editor({"content": {"json": data}}).classes(
            "properties-editor"
        ).on_change(lambda e: _saving(e.content))
