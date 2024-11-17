"""
Minecraft Server Module
"""

import json


server_list = []


def load_servers():
    """
    Function to load server as a MinecraftServer class instance
    """
    with open("config/servers.json", "r", encoding="utf-8") as file:
        servers = json.load(file)

    for server_name, settings in servers.items():
        server_list.append(MinecraftServer(server_name, settings))


class MinecraftServer:
    """
    Minecraft Server class
    This acts as a model for each server
    """

    def __init__(self, name: str, settings: dict):
        self.name = name
        self.settings = settings
        self.running = False
        self.starting = False
        self.stopping = False

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

    def start(self,):
        """Starts the server"""
        self.starting = True
        self.running = True
        self.starting = False
        # raise NotImplementedError()

    def stop(self,):
        """Stops the server"""
        self.stopping = True
        self.running = False
        self.stopping = False
        # raise NotImplementedError()
