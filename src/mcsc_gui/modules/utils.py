"""
Utils
"""

import asyncio
import logging
import os
import platform
import subprocess
from collections.abc import Callable

from nicegui import ui, app

from mcsc import MinecraftServer, suggested_ram_gb, total_ram_gb

from mcsc_gui.modules.server_manager import (
    SERVER_TYPES,
    any_server_active,
    create_server,
    delete_server,
    error_message,
    get_versions,
    send_command,
    stop_all_servers,
    update_server,
)
from mcsc_gui.modules.translations import translate as _
from mcsc_gui.modules.user_settings import UserSettings
from mcsc_gui.config import settings as mcssettings
from mcsc_gui.update import get_current_version, update_mcsc
from mcsc_gui.telemetry import send_event_async

logger = logging.getLogger(__name__)


def get_default_server_settings() -> dict:
    """Return the default values used for creating a server."""
    return {
        "name": "",
        "ram_gb": suggested_ram_gb(),
        "version": "",
        "server_type": 0,
    }


async def send_notification(
    msg: str,
    timeout: None | int = 3,
    spinner: bool = False,
    severity: str = None,
):
    """Sends a notification to the user"""
    if severity not in (None, "positive", "warning", "negative"):
        severity = None
    ui.notification(message=msg, timeout=timeout, spinner=spinner, type=severity)


async def stop_processes():
    """
    Shuts down the app.
    This is a ugly way to close the app but it prevents processes from
    still running in the background (a problem i was having).
    """
    logger.info("Shutting down the app...")
    await stop_all_servers()
    await send_event_async("app_close")

    tasks = {t for t in asyncio.all_tasks() if t is not asyncio.current_task()}
    for task in tasks:
        task.cancel()

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception) and not isinstance(
            result, asyncio.CancelledError
        ):
            logger.error(f"Exception during shutdown: {result}")

    app.shutdown()


def shutdown():
    """Shuts down the app, stopping all servers and processes"""

    def _popup_confirm():
        with ui.dialog() as popup, ui.card().classes("create-server-popup").style(
            "width: 35%"
        ):
            with ui.row().style("width: 100%"):
                ui.label(_("Are you sure?")).style("font-size: 30px;")
            with ui.row().style("width: 100%"):
                ui.label(
                    _("There are still servers running. Are you sure you want to quit?")
                ).style("opacity: 0.6; width: 100%")
            with ui.row().style("width: 100%"):
                ui.button(
                    _("No, take me back"),
                    on_click=popup.close,
                    icon="close",
                ).classes("normal-secondary-button").style("width: 100%")
            with ui.row().style("width: 100%"):
                ui.button(
                    _("Yes, quit"),
                    on_click=lambda: asyncio.create_task(stop_processes()),
                    icon="check",
                ).classes("normal-primary-button").style(
                    "width: 100%; background-color: rgb(216, 68, 68) !important;"
                )
            return popup

    if any_server_active():
        _popup_confirm().open()
    else:
        asyncio.create_task(stop_processes())


def minimize_window():
    """Minimizes the window"""
    app.native.main_window.minimize()


def open_file_explorer(path: str | os.PathLike):
    """Opens file explorer"""
    path = os.fspath(path)
    logger.info(f"Opening file explorer at {path}")
    if platform.system() == "Windows":
        os.startfile(path)  # pylint: disable=no-member
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", path])  # pylint: disable=consider-using-with
    elif platform.system() == "Linux":
        subprocess.Popen(["xdg-open", path])  # pylint: disable=consider-using-with
    else:
        logger.warning("Unsupported operating system")


async def _run_with_notification(caller: ui.button, start_message: str, action, done_message: str) -> bool:
    """
    Run ``action`` (a coroutine function) while showing a progress notification.
    Returns True on success.
    """
    caller.disable()
    n = ui.notification(message=start_message, timeout=None, spinner=True, type="info")
    await asyncio.sleep(0.5)
    try:
        await action()
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"{start_message}: {e}")
        n.spinner = False
        n.type = "negative"
        n.message = error_message(e)
        caller.enable()
        await asyncio.sleep(3)
        n.dismiss()
        return False

    n.spinner = False
    n.type = "positive"
    n.message = done_message
    caller.enable()
    await asyncio.sleep(3)
    n.dismiss()
    return True


def popup_create_server(on_created: Callable[[], None] | None = None):
    """Create server popup window."""
    system_ram = total_ram_gb()
    server_settings = get_default_server_settings()

    async def _create_server(caller: ui.button, settings: dict, eula_accepted: bool):
        async def _action():
            await create_server(
                name=settings.get("name"),
                version=settings.get("version"),
                server_type=settings.get("server_type"),
                ram_gb=settings.get("ram_gb"),
                accept_eula=eula_accepted,
            )

        created = await _run_with_notification(
            caller,
            _("Creating server {name}", name=settings.get("name")),
            _action,
            _("Server created!"),
        )
        if created and on_created is not None:
            on_created()

    with ui.dialog() as popup, ui.card().classes("create-server-popup"):
        with ui.row():
            ui.label(_("New Server")).style("font-size: 30px;")

        with ui.row().style("width: 100%;"):
            ui.input(
                label=_("Server name"),
                validation={_("Too long!"): lambda value: len(value) < 35},
            ).classes("create-server-input").bind_value_to(
                server_settings,
                "name",
            )
            eula = ui.checkbox(_("Accept EULA (Required)")).style(
                "margin-top: 15px !important"
            )

        ui.separator()

        ui.label(_("Dedicated RAM")).style("font-size: 30px;")
        ui.label(
            _("Suggested for this device: {value} GB", value=suggested_ram_gb())
        ).style("opacity: 0.6")
        with ui.row().style("width: 100%; margin-top: 10px;"):
            ui.label("1 GB")
            ui.slider(
                max=system_ram,
                min=1,
                step=1,
            ).classes("create-server-input").style("width: 75%;").props(
                "label-always"
            ).bind_value(
                server_settings, "ram_gb"
            )
            ui.label(f"{system_ram} GB")

        ui.separator()
        ui.label(_("Other settings")).style("font-size: 30px;")

        with ui.row().style("width: 100%;"):
            type_select = (
                ui.select(SERVER_TYPES, with_input=True, label=_("Server Type"))
                .bind_value(server_settings, "server_type")
                .classes("create-server-input")
            )
            version_select = (
                ui.select(
                    get_versions(server_settings["server_type"]),
                    with_input=True,
                    label=_("Server Version"),
                )
                .classes("create-server-input")
                .bind_value(server_settings, "version")
            )

            def _on_type_change():
                version_select.set_value(None)
                version_select.set_options(get_versions(type_select.value or 0))

            type_select.on("update:modelValue", _on_type_change)

        ui.separator()

        with ui.row().style("width: 100%;").style("flex-grow: 1;"):
            ui.button(_("Cancel"), on_click=popup.close, icon="close").classes(
                "normal-secondary-button"
            )
            cb = (
                ui.button(
                    _("Create"),
                    icon="add",
                )
                .classes("normal-primary-button")
                .bind_enabled_from(eula, "value")
            )
            cb.on_click(
                lambda x: _create_server(
                    caller=cb, settings=server_settings, eula_accepted=eula.value
                )
            )
        return popup


def popup_edit_server(server: MinecraftServer):
    """Edit server popup window"""
    system_ram = total_ram_gb()
    form = {
        "name": server.config.name,
        "ram_gb": server.config.ram_gb,
        "server_type": int(server.config.server_type),
        "version": server.config.version,
    }

    async def _edit_server(caller: ui.button):
        async def _action():
            update_server(server, name=form["name"], ram_gb=form["ram_gb"])

        await _run_with_notification(
            caller,
            _("Saving settings of server '{name}'", name=server.name),
            _action,
            _("Settings saved!"),
        )

    with ui.dialog() as popup, ui.card().classes("create-server-popup"):
        with ui.row():
            ui.label(_("Edit Server")).style("font-size: 30px;")

        with ui.row().style("width: 100%;"):
            ui.input(
                label=_("Server name"),
                validation={_("Too long!"): lambda value: len(value) < 35},
            ).classes("create-server-input").bind_value(form, "name")
            ui.checkbox(_("Accept EULA (Required)"), value=server.eula_accepted).style(
                "margin-top: 15px !important"
            ).disable()

        ui.separator()

        ui.label(_("Dedicated RAM")).style("font-size: 30px;")
        ui.label(
            _("Suggested for this device: {value} GB", value=suggested_ram_gb())
        ).style("opacity: 0.6")
        with ui.row().style("width: 100%; margin-top: 10px;"):
            ui.label("1 GB")
            ui.slider(
                max=max(system_ram, form["ram_gb"]),
                min=1,
                step=1,
            ).classes("create-server-input").style("width: 75%;").props(
                "label-always"
            ).bind_value(
                form, "ram_gb"
            )
            ui.label(f"{system_ram} GB")

        ui.separator()
        ui.label(_("Other settings")).style("font-size: 30px;")

        with ui.row().style("width: 100%;"):
            ui.select(SERVER_TYPES, with_input=True, label=_("Server Type")).bind_value(
                form, "server_type"
            ).classes("create-server-input").disable()
            ui.select(
                [form["version"]],
                with_input=True,
                label=_("Server Version"),
            ).classes("create-server-input").bind_value_from(
                form, "version"
            ).disable()

        ui.separator()

        with ui.row().style("width: 100%;").style("flex-grow: 1;"):
            ui.button(_("Cancel"), on_click=popup.close, icon="close").classes(
                "normal-secondary-button"
            )
            cb = ui.button(
                _("Save"),
                icon="save",
            ).classes("normal-primary-button")
            cb.on_click(lambda x: _edit_server(caller=cb))
        return popup


async def write_to_console_and_clean(
    caller, server: MinecraftServer, command: str = ""
):
    """Cleans content of caller after sending input to server"""
    if command:
        await send_command(server, command)
    elif hasattr(caller, "value") and caller.value:
        value = caller.value
        caller.set_value("")
        await send_command(server, value)


def popup_delete_server(server: MinecraftServer):
    """Delete server popup window"""

    async def _delete_server(caller: ui.button, delete_files: bool):
        async def _action():
            await delete_server(server, delete_files=delete_files)

        deleted = await _run_with_notification(
            caller,
            _("Deleting server {name}", name=server.name),
            _action,
            _("Server deleted"),
        )
        if deleted:
            ui.navigate.to("/")

    with ui.dialog() as popup, ui.card().classes("delete-server-popup"):
        with ui.row():
            ui.label(_("Are you sure?")).style("font-size: 30px;")

        with ui.row().style("width: 100%;"):
            ui.label(_("Write '{name}' below to confirm", name=server.name)).style(
                "opacity: 0.6"
            )
            with ui.row().style("width: 100%;"):
                check = ui.input(
                    _("Confirm name"),
                    validation={_("Wrong name"): lambda value: value == server.name},
                ).style("width: 100% !important;")

                delete_files = ui.checkbox(_("Delete server folder"))

            with ui.row().style("width: 100%;").style("flex-grow: 1;"):
                ui.button(_("Cancel"), on_click=popup.close, icon="close").classes(
                    "normal-secondary-button"
                )
                delete_btn = (
                    ui.button(_("Delete"), icon="delete")
                    .classes("normal-primary-button")
                    .style("background-color: rgb(216, 68, 68) !important;")
                )
                delete_btn.bind_enabled_from(
                    check, "value", backward=lambda value: value == server.name
                )
                delete_btn.on_click(
                    lambda x: _delete_server(
                        caller=delete_btn,
                        delete_files=delete_files.value,
                    )
                )

        return popup


def popup_update_app():
    """Update app popup window"""

    async def _update_app(sender: ui.button):
        sender.disable()
        notification = ui.notification(
            _("Updating"), timeout=None, spinner=True, type="info"
        )
        await asyncio.sleep(1)

        # Run update
        # update_task = asyncio.create_task(update_mcsc())
        # await update_task
        result = update_mcsc()

        if result is True:
            notification.spinner = False
            notification.message = _("Update complete. Restart the app")
            notification.type = "positive"
        else:
            notification.message = _("Something went wrong")
            notification.type = "negative"
            sender.enable()

        await asyncio.sleep(10)
        notification.dismiss()

    with ui.dialog() as popup, ui.card().classes("delete-server-popup"):
        with ui.row():
            ui.label(_("Update Available")).style("font-size: 30px;")

        with ui.row().style("width: 100%;"):
            ui.label(
                _("A new version of the app is available. Do you want to update now?")
            ).style("opacity: 0.6")

            # with ui.row().style("width: 100%;"):
            #     ui.label("").bind_text_from(update, "status")

            with ui.row().style("width: 100%;").style("flex-grow: 1;"):
                ui.button(_("Later"), on_click=popup.close, icon="close").classes(
                    "normal-secondary-button"
                )
                ui.button("Update Now", icon="download").classes(
                    "normal-primary-button"
                ).on_click(lambda x: _update_app(x.sender))
        return popup


def popup_app_settings():
    """App settings popup window"""
    user_settings = UserSettings()

    async def _update_settings(**kwargs):
        n = ui.notification(
            message=_("Saving"),
            spinner=True,
            timeout=None,
            type="info",
        )
        await asyncio.sleep(0.5)
        try:
            user_settings.update_settings(**kwargs)
            await send_event_async("settings_change", details=user_settings.user_settings)
            n.spinner = False
            n.type = "positive"
            n.message = _("Settings saved")
        except Exception as e:
            n.spinner = False
            n.type = "negative"
            n.message = str(e)
        finally:
            await asyncio.sleep(3)
            n.dismiss()

    with ui.dialog() as popup, ui.card().classes("delete-server-popup"):
        with ui.row().style("width: 100%;"):
            with ui.grid(rows=1, columns=3):
                ui.image("/static/logo.png").style("width: 100px;")
                ui.label(_("Version: {version}", version=get_current_version())).style(
                    "opacity: 0.6;"
                )
                # ui.link("See changelog").style("opacity: 0.6;").on(
                #     "click", lambda x: ui.navigate.to("/changelog")
                # )

        # with ui.row():
        #     ui.label(_("Settings")).style("font-size: 30px;")

        with ui.row().style("width: 100%;"):
            ui.label(
                _(
                    "Some settings require a restart to take effect. "
                    "Please restart the app after changing them."
                )
            ).style("opacity: 0.6; color: rgb(255, 152, 0)")

        with ui.row().style("width: 100%;"):
            language_select = (
                ui.select(
                    mcssettings.AVAILABLE_LANGAGUES,
                    label=_("Language"),
                    with_input=False,
                    # on_change=lambda x: _update_settings(language=x.value),
                )
                .classes("create-server-input")
                .style("width: 100% !important;")
            )
            language_select.set_value(mcssettings.DEFAULT_LANGUAGE)
            language_select.on_value_change(lambda x: _update_settings(language=x.value))

        with ui.row().style("width: 100%;").style("flex-grow: 1;"):
            ui.button(_("Close"), on_click=popup.close, icon="close").classes(
                "normal-secondary-button"
            ).style("width: 100% !important;")
            # update_btn = (
            #     ui.button(_("Save"), icon="save")
            #     .classes("normal-primary-button")
            #     .on_click(_update_settings)
            # )
        return popup