"""
Utils
"""

import io
import asyncio
import psutil
from nicegui import ui, app
import requests
import pandas as pd

from modules.server import MinecraftServer, full_stop
from config import settings as mcssettings


server_versions = []
server_types = {
    0: "Vanilla",
    # 1: "Spigot",
    # 2: "Forge",
}
vanilla_urls = {}
spigot_urls = {}

urls = None  # pylint: disable=invalid-name


def get_system_total_ram():
    """Total ram on device in GB"""
    return round(psutil.virtual_memory().total / (1024**3))


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


def popup_create_server():
    """Create server popup window"""
    # local variables
    system_ram = get_system_total_ram()
    server_settings = {
        "name": "",
        "dedicated_ram": round(system_ram / 4),
        "version": urls.latest_stable(),
        "jar_type": 0,
        "address": "default",
        "port": 25565,
    }

    async def _create_server(caller: ui.button, settings: dict):
        caller.disable()
        n = ui.notification(
            message=f"Starting creation of server {settings.get('name')}",
            timeout=30,
            spinner=True,
            type="info",
        )
        await asyncio.sleep(1)
        try:
            server_name = settings.get("name").strip()
            assert server_name != "", "Server name can't be empty"
            # if not settings.get("address"):
            #     raise ValueError("Server address can't be empty")

            # # address is present: check if it is a valid ip address
            # try:
            #     ipaddress.IPv4Address(settings.get("address"))
            # except ipaddress.AddressValueError as e:
            #     raise ValueError("Invalid IPv4 address") from e

            MinecraftServer(settings=settings.copy())
            # Reset settings and name
            settings = {
                "name": "",
                "dedicated_ram": round(system_ram / 4),
                "version": urls.latest_stable(),
                "jar_type": 0,
                "address": "default",
                "port": 25565,
            }

            # notify user
            caller.enable()
            n.spinner = False
            n.type = "positive"
            n.message = "Server created!"
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
            ui.label("New Server").style("font-size: 30px;")

        with ui.row().style("width: 100%;"):
            ui.input(
                label="Server name",
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
            eula = ui.checkbox("Accept EULA (Required)").style(
                "margin-top: 15px !important"
            )

        ui.separator()

        ui.label("Dedicated RAM").style("font-size: 30px;")
        ui.label(f"Suggested for this device: {round(system_ram/4)}GB").style(
            "opacity: 0.6"
        )
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
                server_settings, "dedicated_ram"
            )
            ui.label(f"{system_ram} GB")

        ui.separator()
        ui.label("Other settings").style("font-size: 30px;")

        with ui.row().style("width: 100%;"):
            ui.select(server_types, with_input=True, label="Server Type").bind_value(
                server_settings, "jar_type"
            ).classes("create-server-input")
            ui.select(server_versions, with_input=True, label="Server Version").classes(
                "create-server-input"
            ).bind_value(server_settings, "version")

        ui.separator()

        with ui.row().style("width: 100%;").style("flex-grow: 1;"):
            ui.button("Cancel", on_click=popup.close, icon="close").classes(
                "normal-secondary-button"
            )
            cb = (
                ui.button(
                    "Create",
                    icon="add",
                )
                .classes("normal-primary-button")
                .bind_enabled_from(eula, "value")
            )
            cb.on_click(lambda x: _create_server(caller=cb, settings=server_settings))
        return popup


def load_server_versions():
    """Loads server versions"""
    response = requests.get(mcssettings.VERSION_LIST_URL, timeout=10)
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
                value = ver.replace(".", "")
                if value.isnumeric():
                    filtered_list.append(ver)
            return filtered_list

        return version_list


def popup_edit_server(server: MinecraftServer):
    """Create server popup window"""
    # bind setting to inputs
    system_ram = get_system_total_ram()

    async def _edit_server(caller: ui.button, server: MinecraftServer):
        caller.disable()
        n = ui.notification(
            message=f"Saving settings of server '{server.name}'",
            timeout=None,
            spinner=True,
            type="info",
        )
        await asyncio.sleep(1)
        try:
            server.name = server.name.strip()
            assert server.name != "", "Server name can't be empty"
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
            n.message = "Settings saved!"
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
            ui.label("Edit Server").style("font-size: 30px;")

        with ui.row().style("width: 100%;"):
            ui.input(
                label="Server name",
                validation={"Too long!": lambda value: len(value) < 35},
            ).classes("create-server-input").bind_value(server.settings, "name")
            # ui.input(
            #     label="IPv4 Address",
            #     validation={"Too long!": lambda value: len(value) < 16},
            # ).classes("create-server-input").bind_value(
            #     server.settings,
            #     "address",
            # )
            ui.checkbox("Accept EULA (Required)", value=True).style(
                "margin-top: 15px !important"
            ).disable()

        ui.separator()

        ui.label("Dedicated RAM").style("font-size: 30px;")
        ui.label(f"Suggested for this device: {round(system_ram/4)}GB").style(
            "opacity: 0.6"
        )
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
        ui.label("Other settings").style("font-size: 30px;")

        with ui.row().style("width: 100%;"):
            ui.select(server_types, with_input=True, label="Server Type").bind_value(
                server.settings, "jar_type"
            ).classes("create-server-input").disable()
            ui.select(server_versions, with_input=True, label="Server Version").classes(
                "create-server-input"
            ).bind_value(server.settings, "version").disable()

        ui.separator()

        with ui.row().style("width: 100%;").style("flex-grow: 1;"):
            ui.button("Cancel", on_click=popup.close, icon="close").classes(
                "normal-secondary-button"
            )
            cb = ui.button(
                "Save",
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
            message=f"Deleting server {server.name}",
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
            n.message = "Server deleted"
            await asyncio.sleep(3)
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
            ui.label("Are you sure?").style("font-size: 30px;")

        with ui.row().style("width: 100%;"):
            ui.label(f"Write '{server.name}' below to confirm").style("opacity: 0.6")
            with ui.row().style("width: 100%;"):
                check = ui.input(
                    "Confirm name",
                    validation={"Wrong name": lambda value: value == server.name},
                ).style("width: 100% !important;")

                delete_files = ui.checkbox("Delete server folder")

            with ui.row().style("width: 100%;").style("flex-grow: 1;"):
                ui.button("Back", on_click=popup.close, icon="close").classes(
                    "normal-secondary-button"
                )
                delete_btn = (
                    ui.button("Delete", icon="delete")
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
