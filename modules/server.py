"""
Minecraft Server Module
"""

import json
import os
from uuid import uuid4
import requests
from nicegui import binding

from config import settings as mcssettings


server_list = []

global_settings = {}


def load_servers():
    """
    Function to load server as a MinecraftServer class instance
    """
    if not os.path.exists(mcssettings.SERVERS_JSON_PATH):
        with open(mcssettings.SERVERS_JSON_PATH, "w", encoding="utf-8") as file:
            file.write("{}")
            file.flush()
        return

    with open(mcssettings.SERVERS_JSON_PATH, "r", encoding="utf-8") as file:
        servers = json.load(file)

    global global_settings  # pylint: disable=global-statement
    global_settings = servers

    for server_name, settings in servers.items():
        MinecraftServer(server_name, settings)


class MinecraftServer:
    """
    Minecraft Server class
    This acts as a model for each server
    """

    name = binding.BindableProperty()
    settings = binding.BindableProperty()

    def __init__(self, name: str = "", settings: dict = None):
        self.name = name
        self.settings = settings or {}
        self.running = False
        self.starting = False
        self.stopping = False

        if not settings.get("uuid"):
            global global_settings  # pylint: disable=global-statement
            if name in global_settings.keys():
                raise ValueError(f"A server with the name {name} already exists")
            self._create_server()

        # add self to server_list
        server_list.append(self)

    def __repr__(self):
        return f"<MinecraftServer: {self.name!r} addr={self.socket_address}>"

    def __str__(self):
        return self.name

    @property
    def status(self):
        """Display-friendly status of the server"""
        if any([self.starting, self.stopping]):
            if self.starting and self.running is False:
                return "Starting..."
            if self.stopping and self.running is True:
                return "Stopping..."

        return "Running" if self.running else "Stopped"

    @property
    def properties(self):
        """
        Loads server.properties file from server's directory
        and builds a dictionary
        """
        return {}

    @property
    def address(self):
        """ip address"""
        return self.settings.get("address", "undefined")

    @property
    def port(self):
        """port number"""
        return self.settings.get("port", "undefined")

    @property
    def socket_address(self):
        """display friendly socked addres"""
        return f"{self.address}:{self.port}"

    @property
    def version(self):
        """display friendly server version"""
        return self.settings["version"]

    @property
    def jar_type(self):
        """display friendly jar type"""
        return self.settings["jar_type"]

    @property
    def uuid(self):
        """return uuid"""
        return self.settings["uuid"]

    def _create_server(self):
        """
        Actually creates the server on the device
        Order of actions:
        - create server folder
        - download jar and place it inside folder
        - eula
        - create start.bat (maybe not?)
        """
        self.settings["uuid"] = str(uuid4())
        self.settings["folder_path"] = os.path.join(
            os.getcwd(), "servers", self.settings["uuid"]
        )
        # create server folder
        os.mkdir(self.settings["folder_path"])
        assert os.path.exists(self.settings["folder_path"])

        # download jar
        self._download_jar()

        # accept eula
        with open(os.path.join(self.settings["folder_path"], "eula.txt"), "w") as eula:
            eula.write("eula=true")

        # save into server.json
        self._save_server()

    def _download_jar(self):
        """downloads jar"""
        # get jar link
        from modules.utils import urls  # pylint: disable=import-outside-toplevel

        url = urls.get_url(self.version, self.jar_type)
        file_path = os.path.join(self.settings["folder_path"], "server.jar")
        try:
            response = requests.get(url, stream=True)  # pylint: disable=missing-timeout
            response.raise_for_status()
            with open(file_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)
            print(f"downloaded {file_path}")

        except requests.exceptions.RequestException as e:
            print(f"Error downloading the file: {e}")
            raise

        except Exception as e:
            print(f"{e}")
            raise

    def _save_server(self):
        """Saves instance settings into servers.json file"""
        try:
            with open(mcssettings.SERVERS_JSON_PATH, "w", encoding="utf-8") as file:
                global global_settings  # pylint: disable=global-statement
                if self.name in global_settings.keys():
                    # FIXME: maybe check before creating and downloading jar...
                    raise ValueError(
                        f"A server with the name {self.name} already exists"
                    )

                # update global_settings
                global_settings[self.name] = self.settings
                # save global_settings
                json.dump(global_settings, file, indent=4)
        except Exception as e:
            print(f"Can't save servers: {e}")
            raise

        print(f"Server {self.name} with uuid {self.uuid} saved!")

    def start(
        self,
    ):
        """Starts the server"""
        self.starting = True
        self.running = True
        self.starting = False
        # raise NotImplementedError()

    def stop(
        self,
    ):
        """Stops the server"""
        self.stopping = True
        self.running = False
        self.stopping = False
        # raise NotImplementedError()
