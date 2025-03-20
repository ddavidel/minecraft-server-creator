"""
Server related utility functions and classes
"""

import json
import os

from config import settings as mcssettings
from modules.translations import translate as _
from modules.servers.models import (
    MinecraftServer,
    get_server_list,
    get_global_settings,
    set_global_settings,
    add_server_to_list,
)
from modules.servers.forge import ForgeServer
from modules.servers.java import JavaServer


TYPE_TO_CLASS = {
    0: JavaServer,
    # 1: SpigotServer,
    2: ForgeServer,
}


def create_server(settings: dict):
    """
    Use this function to successfully create a server on MCSC.
    This function handles all the necessary steps to create a server.
    Its higly recommended to use this function to create a server.
    """
    TYPE_TO_CLASS[settings["jar_type"]](settings=settings)


def load_servers():
    """
    Function to load server as a MinecraftServer class instance
    """
    if not os.path.exists(mcssettings.SERVERS_JSON_PATH):
        with open(mcssettings.SERVERS_JSON_PATH, "w", encoding="utf-8") as file:
            file.write("{}")
            file.flush()

        os.makedirs("servers", exist_ok=True)
        return

    with open(mcssettings.SERVERS_JSON_PATH, "r", encoding="utf-8") as file:
        servers = json.load(file)

    # Set global settings
    set_global_settings(servers)

    for server_uuid, settings in servers.items():
        TYPE_TO_CLASS[settings["jar_type"]](
            settings=settings, uuid=server_uuid
        )


def get_server_by_name(server_name: str) -> MinecraftServer | None:
    """
    Returns server instance found by name.
    Probably not gonna be used
    """
    for server in get_server_list():
        if server.name == server_name:
            return server
    return None


def get_server_by_uuid(uuid: str) -> MinecraftServer | None:
    """
    Returns server instance by by uuid.
    """
    for server in get_server_list():
        if server.uuid == uuid:
            return server
    return None


async def full_stop():
    """Ensures all servers are stopped"""
    for server in get_server_list():
        if server.running and server.process:
            await server.stop()
