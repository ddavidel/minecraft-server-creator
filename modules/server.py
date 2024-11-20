"""
Minecraft Server Module
"""

import asyncio
import json
import os
import subprocess
import threading
from uuid import uuid4
import numpy as np
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
        self.process = None

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
    def address(self) -> str:
        """ip address"""
        return self.settings.get("address", "undefined")

    @property
    def port(self) -> int:
        """port number"""
        return self.settings.get("port", np.nan)

    @property
    def socket_address(self) -> str:
        """display friendly socked addres"""
        return f"{self.address}:{self.port}"

    @property
    def version(self) -> str:
        """display friendly server version"""
        return self.settings["version"]

    @property
    def jar_type(self) -> int:
        """display friendly jar type"""
        return self.settings["jar_type"]

    @property
    def uuid(self) -> str:
        """return uuid"""
        return self.settings["uuid"]

    @property
    def jar_path(self) -> str:
        """server's jar path"""
        return os.path.join(self.settings["folder_path"], "server.jar")

    @property
    def server_path(self) -> str:
        """server's jar path"""
        return self.settings["folder_path"]

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

    async def start(self):
        """Starts the server"""
        self.starting = True
        try:
            # Command to start the server
            cmd = ["java", "-Xmx1G", "-Xms1G", "-jar", self.jar_path, "nogui"]

            # Start the subprocess
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.server_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )

            # Start tasks for reading output and taking input
            output_task = asyncio.create_task(self._console_reader())
            input_task = asyncio.create_task(self._console_writer())

            self.running = True
            self.starting = False
            print("Server started. Type commands below:")

            # Wait for the server process to finish
            await self.process.wait()

            # Cancel input and output tasks once the server stops
            input_task.cancel()
            await asyncio.gather(input_task, output_task, return_exceptions=True)

            print("Server stopped.")

        except FileNotFoundError as e:
            print(f"Error: {e}")

        except Exception as e:
            print(f"An error occurred: {e}")

        finally:
            self.starting = False
            self.running = False

    async def stop(self):
        """Stops the server"""
        self.stopping = True
        if self.process:
            self.process.terminate()
            await self.process.wait()
            self.process = None
            self.running = False
            self.stopping = False
            print("Server stopped.")

    async def _console_writer(self):
        """Reads user input and sends it to the server."""
        try:
            while self.running:
                command = await asyncio.to_thread(input, ">>> ")
                if self.process and self.process.stdin:
                    self.process.stdin.write(command + "\n")
                    await self.process.stdin.drain()
        except Exception as e:
            print(f"Writer error: {e}")

    async def _console_reader(self) -> str:
        """reads and prints console output"""
        try:
            while self.running:
                line = await self.process.stdout.readline()
                if line:
                    print(line.decode().strip())
                else:
                    break
        except Exception as e:
            print(f"Reader error: {e}")
