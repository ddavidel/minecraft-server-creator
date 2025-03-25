"""
Utils
"""

import os
import asyncio
import platform
import psutil
from nicegui import ui, app
import requests

from modules.servers.models import MinecraftServer
from modules.servers.utils import full_stop, create_server
from modules.translations import translate as _
from modules.user_settings import update_settings
from config import settings as mcssettings
from update import Update, get_current_version


server_versions = []
server_types = {
    0: "Vanilla",
    # 1: "Spigot",
    2: "Forge",
}

urls = None  # pylint: disable=invalid-name


def get_system_total_ram():
    """Total ram on device in GB"""
    return round(psutil.virtual_memory().total / (1024**3))


def get_suggested_ram() -> int | float:
    """
    Suggested ram for server in GB.
    This makes sense for most servers since its usually better
    to have a server with 4~6GB of ram.
    However, if a server has lots of mods or plugins, it may need more ram.
    """
    value = round(get_system_total_ram() / 4)
    if value > 6:
        return 6
    return value


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
    await full_stop()

    tasks = {t for t in asyncio.all_tasks() if t is not asyncio.current_task()}
    for task in tasks:
        task.cancel()

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception) and not isinstance(
            result, asyncio.CancelledError
        ):
            print(f"Exception during shutdown: {result}")

    app.shutdown()


def shutdown():
    """Shuts down the app, stopping all servers and processes"""
    asyncio.create_task(stop_processes())


def minimize_window():
    """Minimizes the window"""
    app.native.main_window.minimize()


def open_file_explorer(path: str):
    """Opens file explorer"""
    if platform.system() == "Windows":
        os.startfile(path)
    elif platform.system() == "Darwin":  # This is macOS according to ChatGPT
        os.system(f"open {path}")
    elif platform.system() == "Linux":
        os.system(f"xdg-open {path}")
    else:
        print("Unsupported operating system")


def popup_create_server():
    """Create server popup window"""
    # local variables
    system_ram = get_system_total_ram()
    server_settings = {
        "name": "",
        "dedicated_ram": get_suggested_ram(),
        "version": "",
        "jar_type": 0,
        "address": "default",
        "port": 25565,
    }

    async def _create_server(caller: ui.button, settings: dict):
        caller.disable()
        n = ui.notification(
            message=_("Creating server {name}", name=settings.get("name")),
            timeout=None,
            spinner=True,
            type="info",
        )
        await asyncio.sleep(1)
        try:
            assert settings.get("name", "") != "", _("Server name can't be empty")
            assert settings.get("version", None), _("Server version can't be empty")

            # Initialize server
            create_server(settings=settings.copy())

            # Reset settings and name
            settings = {
                "name": "",
                "dedicated_ram": get_suggested_ram(),
                "version": "",
                "jar_type": 0,
                "address": "default",
                "port": 25565,
            }

            # Notify user
            caller.enable()
            n.spinner = False
            n.type = "positive"
            n.message = _("Server created!")
            await asyncio.sleep(3)
            n.dismiss()

        except Exception as e:
            caller.enable()
            n.spinner = False
            n.type = "negative"
            n.message = str(e)
            await asyncio.sleep(3)
            n.dismiss()

        caller.enable()

    with ui.dialog() as popup, ui.card().classes("create-server-popup"):
        with ui.row():
            ui.label(_("New Server")).style("font-size: 30px;")

        with ui.row().style("width: 100%;"):
            ui.input(
                label=_("Server name"),
                validation={"Too long!": lambda value: len(value) < 35},
            ).classes("create-server-input").bind_value_to(
                server_settings,
                "name",
            )  # .style("width: 100% !important")
            # ui.input(
            #     label="IPv4 Address",
            #     validation={"Too long!": lambda value: len(value) < 16},
            # ).classes("create-server-input").bind_value_to(
            #     server_settings,
            #     "address",
            # )
            eula = ui.checkbox(_("Accept EULA (Required)")).style(
                "margin-top: 15px !important"
            )

        ui.separator()

        ui.label(_("Dedicated RAM")).style("font-size: 30px;")
        ui.label(
            _("Suggested for this device: {value} GB", value=get_suggested_ram())
        ).style("opacity: 0.6")
        with ui.row().style("width: 100%; margin-top: 10px;"):
            ui.label("1 GB")
            ui.slider(
                max=system_ram,
                min=1,
                step=1,
                value=get_suggested_ram(),
            ).classes("create-server-input").style("width: 75%;").props(
                "label-always"
            ).bind_value(
                server_settings, "dedicated_ram"
            )
            ui.label(f"{system_ram} GB")

        ui.separator()
        ui.label(_("Other settings")).style("font-size: 30px;")

        with ui.row().style("width: 100%;"):
            type_select = (
                ui.select(server_types, with_input=True, label=_("Server Type"))
                .bind_value(server_settings, "jar_type")
                .classes("create-server-input")
            )
            version_select = (
                ui.select(
                    urls.get_versions_for_type(0),
                    with_input=True,
                    label=_("Server Version"),
                )
                .classes("create-server-input")
                .bind_value(server_settings, "version")
            )

            type_select.on(
                "update:modelValue",
                lambda x: version_select.set_options(
                    urls.get_versions_for_type(type_select.value)
                ),
            )

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
            cb.on_click(lambda x: _create_server(caller=cb, settings=server_settings))
        return popup


def _load_vanilla_versions() -> dict:
    """Loads vanilla versions"""
    response = requests.get(mcssettings.VANILLA_VERSION_LIST_URL, timeout=10)
    response.raise_for_status()
    vanilla_dict = response.json()
    return vanilla_dict


def _load_spigot_versions() -> dict:
    """Loads spigot versions"""
    raise NotImplementedError()


def _load_forge_versions() -> dict:
    """Loads forge versions"""
    response = requests.get(mcssettings.FORGE_VERSION_LIST_URL, timeout=10)
    response.raise_for_status()
    forge_dict = response.json()

    # atm mcsc works only with forge version from 1.17.0
    # so we need to remove the previous versions
    filtered_dict = {}
    for version in forge_dict.keys():
        text_version = version.split("-")[0].replace(".", "").strip("0")
        if text_version.isnumeric():
            version_number = int(text_version)
            if version_number >= 1170:
                filtered_dict[version] = forge_dict[version]
    return filtered_dict


def load_server_versions():
    """Loads server versions"""
    global urls  # pylint:disable=global-statement

    # Retrieve versions data
    vanilla_dict = _load_vanilla_versions()
    # spigot_dict = _load_spigot_versions()
    forge_dict = _load_forge_versions()

    # Set urls
    urls = JarUrl()
    urls.set_urls(jar_type=0, data_dict=vanilla_dict)
    # urls.set_urls(jar_type=1, data_dict={})
    urls.set_urls(jar_type=2, data_dict=forge_dict)


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
        # self.update_version_list()

    def get_url(self, version: str, jar_type: int) -> str:
        """returns url of version"""
        if jar_type == 0:
            # vanilla url
            if not self.vanilla_urls.get(version):
                raise ValueError(_("Version URL not found"))
            return self.vanilla_urls.get(version)

        if jar_type == 1:
            # spigot url
            if not self.spigot_urls.get(version):
                raise ValueError(_("Version URL not found"))
            return self.spigot_urls.get(version)

        if jar_type == 2:
            # forge url
            if not self.forge_urls.get(version):
                raise ValueError(_("Version URL not found"))
            return self.forge_urls.get(version)

    def update_version_list(self):
        """updates server versions list"""
        global server_versions  # pylint:disable=global-statement
        version_list = (
            list(self.vanilla_urls.keys())
            + list(self.spigot_urls.keys())
            + list(self.forge_urls.keys())
        )
        server_versions = self.filter_version_list(version_list=list(set(version_list)))

    def latest_stable(self):
        """Returns latest stable version"""
        return max(
            (
                ver
                for ver in server_versions
                if ver.replace(".", "").strip("0").isnumeric()
            ),
            key=lambda ver: int(ver.replace(".", "").strip("0")),
            default=server_versions[0],
        )

    def filter_version_list(self, version_list) -> list:
        """filter server list using filter from settings"""
        if mcssettings.JAR_VERSIONS_FILTER == "none":
            return version_list

        if mcssettings.JAR_VERSIONS_FILTER == "stable":
            # only stable versions
            filtered_list = []
            for ver in version_list:
                value = ver.replace(".", "").replace("-", "").strip()
                if value.isnumeric():
                    filtered_list.append(ver)
            return filtered_list

        return version_list

    def set_version_list(self, event, version_select: ui.select):
        """sets version list"""
        global server_versions  # pylint:disable=global-statement

        # Gather data
        jar_type = event.sender.value or 0

        data = []
        if jar_type == 0:
            data = list(self.vanilla_urls.keys())
        elif jar_type == 1:
            data = list(self.spigot_urls.keys())
        elif jar_type == 2:
            data = list(self.forge_urls.keys())

        server_versions = self.filter_version_list(version_list=list(set(data)))
        version_select.set_options(server_versions)

    def get_versions_for_type(self, jar_type: int) -> list:
        """returns versions for type"""
        data = []
        if jar_type == 0:
            data = list(self.vanilla_urls.keys())
        elif jar_type == 1:
            data = list(self.spigot_urls.keys())
        elif jar_type == 2:
            data = list(self.forge_urls.keys())

        return self.filter_version_list(version_list=list(set(data)))


def popup_edit_server(server: MinecraftServer):
    """Create server popup window"""
    # bind setting to inputs
    system_ram = get_system_total_ram()

    async def _edit_server(caller: ui.button, server: MinecraftServer):
        caller.disable()
        n = ui.notification(
            message=_("Saving settings of server '{name}'", name=server.name),
            timeout=None,
            spinner=True,
            type="info",
        )
        await asyncio.sleep(1)
        try:
            server.name = server.name.strip()
            assert server.name != "", _("Server name can't be empty")
            # if not server.address:
            #     raise ValueError("Server address can't be empty")

            # # address is present: check if it is a valid ip address
            # try:
            #     ipaddress.IPv4Address(server.address)
            # except ipaddress.AddressValueError as e:
            #     raise ValueError("Invalid IPv4 address") from e

            # validation completed. save new settings.
            server.save()

            # notify user
            caller.enable()
            n.spinner = False
            n.type = "positive"
            n.message = _("Settings saved!")
            await asyncio.sleep(3)
            n.dismiss()

        except Exception as e:
            caller.enable()
            n.spinner = False
            n.type = "negative"
            n.message = str(e)
            await asyncio.sleep(3)
            n.dismiss()

        caller.enable()

    with ui.dialog() as popup, ui.card().classes("create-server-popup"):
        with ui.row():
            ui.label(_("Edit Server")).style("font-size: 30px;")

        with ui.row().style("width: 100%;"):
            ui.input(
                label=_("Server name"),
                validation={_("Too long!"): lambda value: len(value) < 35},
            ).classes("create-server-input").bind_value(server.settings, "name")
            # ui.input(
            #     label="IPv4 Address",
            #     validation={"Too long!": lambda value: len(value) < 16},
            # ).classes("create-server-input").bind_value(
            #     server.settings,
            #     "address",
            # )
            ui.checkbox(_("Accept EULA (Required)"), value=True).style(
                "margin-top: 15px !important"
            ).disable()

        ui.separator()

        ui.label(_("Dedicated RAM")).style("font-size: 30px;")
        ui.label(
            _("Suggested for this device: {value} GB", value=round(system_ram / 4))
        ).style("opacity: 0.6")
        with ui.row().style("width: 100%; margin-top: 10px;"):
            ui.label("1 GB")
            ui.slider(
                max=system_ram,
                min=1,
                step=1,
                value=round(system_ram / 4),
            ).classes("create-server-input").style("width: 75%;").props(
                "label-always"
            ).bind_value(
                server.settings, "dedicated_ram"
            )
            ui.label(f"{system_ram} GB")

        ui.separator()
        ui.label(_("Other settings")).style("font-size: 30px;")

        with ui.row().style("width: 100%;"):
            ui.select(server_types, with_input=True, label=_("Server Type")).bind_value(
                server.settings, "jar_type"
            ).classes("create-server-input").disable()
            ui.select(
                urls.get_versions_for_type(server.jar_type), with_input=True, label=_("Server Version")
            ).classes("create-server-input").bind_value_from(
                server.settings, "version"
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
            cb.on_click(lambda x: _edit_server(caller=cb, server=server))
        return popup


async def write_to_console_and_clean(
    caller, server: MinecraftServer, command: str = ""
):
    """Cleans content of caller after sending input to server"""
    if command:
        await server.console_writer(command=command)
    elif hasattr(caller, "value") and caller.value:
        await server.console_writer(caller.value)
        caller.set_value("")


def popup_delete_server(server: MinecraftServer):
    """Create server popup window"""

    async def _delete_server(
        caller: ui.button, server: MinecraftServer, delete_files: bool
    ):
        caller.disable()
        n = ui.notification(
            message=_("Deleting server {name}", name=server.name),
            timeout=None,
            spinner=True,
            type="info",
        )
        await asyncio.sleep(1)
        try:
            # delete server
            server.delete(delete_dir=delete_files)

            # notify user
            n.spinner = False
            n.type = "positive"
            n.message = _("Server deleted")
            await asyncio.sleep(1.5)
            n.dismiss()
            ui.navigate.to("/")

        except Exception as e:
            caller.enable()
            n.spinner = False
            n.type = "negative"
            n.message = str(e)
            await asyncio.sleep(3)
            n.dismiss()

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
                        server=server,
                        delete_files=delete_files.value,
                    )
                )

        return popup


def popup_update_app():
    """Update app popup window"""
    update = Update()

    async def _update_app(sender: ui.button):
        sender.disable()
        notification = ui.notification(
            _("Updating"), timeout=None, spinner=True, type="info"
        )
        await asyncio.sleep(1)

        # Run update
        update_task = asyncio.create_task(update.run())
        await update_task

        notification.spinner = False
        if update.completed:
            notification.message = _("Update complete. Restart the app")
            notification.type = "positive"
        else:
            notification.message = _("Something went wrong")
            notification.type = "negative"
            sender.enable()

        await asyncio.sleep(5)
        notification.dismiss()

    with ui.dialog() as popup, ui.card().classes("delete-server-popup"):
        with ui.row():
            ui.label(_("Update Available")).style("font-size: 30px;")

        with ui.row().style("width: 100%;"):
            ui.label(
                _("A new version of the app is available. Do you want to update now?")
            ).style("opacity: 0.6")

            with ui.row().style("width: 100%;"):
                ui.label("").bind_text_from(update, "status")

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

    async def _update_settings(**kwargs):
        n = ui.notification(
            message=_("Saving"),
            spinner=True,
            timeout=None,
            type="info",
        )
        await asyncio.sleep(0.5)
        try:
            update_settings(**kwargs)
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
