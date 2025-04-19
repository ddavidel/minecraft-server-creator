"""
Spigot server module
"""

from modules.translations import translate as _

from modules.servers.models import MinecraftServer
from modules.logger import RotatingLogger


logger = RotatingLogger()


class SpigotServer(MinecraftServer):
    """
    Spigot Server Model
    """

    VERSION_LIST_URL = "https://raw.githubusercontent.com/ddavidel/minecraft-server-jars/refs/heads/main/versions/spigot_version_list.json"

    @classmethod
    def get_versions(cls):
        """
        """
