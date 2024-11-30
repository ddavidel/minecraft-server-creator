"""
Minecraft Server Module
"""

import asyncio
import json
import os
import shutil
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

    for server_uuid, settings in servers.items():
        MinecraftServer(settings=settings, uuid=server_uuid)


class MinecraftServer:
    """
    Minecraft Server class
    This acts as a model for each server
    """

    name = binding.BindableProperty()
    settings = binding.BindableProperty()

    def __init__(self, settings: dict, uuid: str = ""):
        # Setup attributes
        self.name = settings.get("name")
        self.settings = settings or {}
        self.running = False
        self.starting = False
        self.stopping = False
        self.process = None
        self.log = None
        self.server_properties = {}

        if not uuid:
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

    @property
    def has_server_properties(self) -> bool:
        """Returns true if server.properties is in server dir"""
        return os.path.exists(os.path.join(self.server_path, "server.properties"))

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
        with open(
            os.path.join(self.settings["folder_path"], "eula.txt"),
            mode="w",
            encoding="utf-8",
        ) as eula:
            eula.write("eula=true")

        # save into server.json
        self.save()

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

    def _save_settings(self):
        """saves global settings to servers.json"""
        with open(mcssettings.SERVERS_JSON_PATH, "w", encoding="utf-8") as file:
            # save global_settings
            json.dump(global_settings, file, indent=4)

    def save(self):
        """Saves instance settings into servers.json file"""
        try:
            # update global_settings
            global_settings[self.uuid] = self.settings
            # save global_settings
            self._save_settings()
            # update name
            self.name = self.settings.get("name")

        except Exception as e:
            print(f"Can't save servers: {e}")
            raise

        print(f"Server {self.uuid} saved!")

    async def start(self):
        """Starts the server"""
        self.starting = True
        try:
            cmd = [
                "java",
                # f"-d{mcssettings.JAVA_BIT_MODEL}",
                f"-Xmx{self.settings['dedicated_ram']}G",
                f"-Xms{self.settings['dedicated_ram']}G",
                "-jar",
                self.jar_path,
                "nogui" if mcssettings.NOGUI else "",
            ]

            # Start the subprocess
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.server_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            # Start tasks for reading output and taking input
            output_task = asyncio.create_task(self._console_reader())
            # input_task = asyncio.create_task(self.console_writer())

            self.running = True
            self.starting = False

            # Wait for the server process to finish
            await self.process.wait()

            self.running = False

            # Cancel input and output tasks once the server stops
            await asyncio.gather(output_task, return_exceptions=True)

        except FileNotFoundError as e:
            print(f"Error: {e}")

        except Exception as e:
            print(f"An error occurred: {e}")

        finally:
            self.starting = False
            self.running = False

    async def stop(self):
        """Stops the server"""
        if self.process and self.running:
            print("Stopping the server...")
            try:
                # Send the 'stop' command to the server
                if self.process.stdin:
                    self.process.stdin.write(b"stop\n")
                    await self.process.stdin.drain()

                # Wait for the process to terminate gracefully
                await self.process.wait()
                print("Server stopped.")
            except Exception as e:
                print(f"Error while stopping the server: {e}")
            finally:
                # Ensure process cleanup
                self.process = None
                self.running = False
                self.stopping = False
        else:
            print("Server is not running.")

    async def console_writer(self, command: str):
        """Reads user input and sends it to the server."""
        try:
            if self.running:
                # command = await asyncio.to_thread(input)
                if self.process and self.process.stdin and command == "stop":
                    await self.stop()

                elif self.process and self.process.stdin:
                    self.process.stdin.write((command + "\n").encode())
                    await self.process.stdin.drain()
        except Exception as e:
            print(f"Writer error: {e}")

    async def _console_reader(self) -> str:
        """reads and prints console output"""
        try:
            while self.running:
                line = await self.process.stdout.readline()
                if self.log and line:
                    self.log.push(line.decode().strip())
                elif not line:
                    break
        except Exception as e:
            print(f"Reader error: {e}")

    def delete(self, delete_dir: bool = False):
        """Deletes the server from servers.json"""
        if delete_dir:
            for item in os.listdir(self.server_path):
                item_path = os.path.join(self.server_path, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.unlink(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                except Exception as e:
                    print(f"Failed to delete {item_path}: {e}")
            # remove server dir
            shutil.rmtree(self.server_path)

        # remove from server_list
        assert self in server_list, "Invalid server"
        server_list.remove(self)

        # remove from global_settings
        assert global_settings[self.uuid], "Invalid server"
        del global_settings[self.uuid]

        # update settings
        try:
            self._save_settings()

        except Exception as e:
            print(f"Can't delete server: {e}")
            raise

        print(f"Deleted server {self.uuid}")

    def load_server_properties(self):
        """Loads server.properties file"""
        if self.has_server_properties:
            with open(
                os.path.join(self.server_path, "server.properties"),
                mode="r",
                encoding="utf-8",
            ) as properties:
                for line in properties:
                    if line.strip() and not line.startswith("#"):
                        key, value = line.strip().split("=", 1)
                        self.server_properties[key] = value

    def save_server_properties(self):
        """Saves server.properties file"""
        raise NotImplementedError()
        if self.has_server_properties and self.server_properties is not None:
            with open(
                os.path.join(self.server_path, "server.properties"),
                mode="w",
                encoding="utf-8",
            ) as properties:
                self.server_properties = properties.readlines()


def get_server_by_name(server_name: str) -> MinecraftServer | None:
    """
    Returns server instance found by name.
    Probably not gonna be used
    """
    for server in server_list:
        if server.name == server_name:
            return server
    return None


def get_server_by_uuid(uuid: str) -> MinecraftServer | None:
    """
    Returns server instance by by uuid.
    """
    for server in server_list:
        if server.uuid == uuid:
            return server
    return None


def full_stop():
    """Ensures all servers are stopped"""
    for server in server_list:
        if server.running and server.process:
            server.stop()
