"""
Paper server module
"""

import os
import yaml

from mcsc.modules.translations import translate as _

from mcsc.modules.servers.models import MinecraftServer
from mcsc.modules.logger import RotatingLogger


logger = RotatingLogger()

FILE_TO_ATTR = {
    "spigot.yml": "spigot_properties",
    "paper.yml": "paper_properties",
}


class PaperServer(MinecraftServer):
    """
    Paper Server Model
    """

    def __init__(self, settings, uuid=""):
        self.spigot_properties = {}
        self.paper_properties = {}
        super().__init__(settings, uuid)

    @property
    def has_spigot_yml(self):
        """
        Check if the server has a spigot.yml file
        """
        return os.path.exists(os.path.join(self.server_path, "spigot.yml"))

    @property
    def has_paper_yml(self):
        """
        Check if the server has a spigot.yml file
        """
        return os.path.exists(os.path.join(self.server_path, "paper.yml"))

    def load_yml(self, filename: str) -> dict:
        """
        Load a file in server directory. This could easily be
        a method in the MinecraftServer class as a generic load_file
        method, but that will be done in the future.

        Args:
            filename (str): filename to load

        Returns:
            loaded file as a dict
        """
        if not os.path.exists(os.path.join(self.server_path, filename)):
            logger.error(_("File not found"))
            return {}

        with open(
            os.path.join(self.server_path, filename), "r", encoding="utf-8"
        ) as file:
            data = yaml.safe_load(file)

        logger.info(f"Loaded {filename} for server {self.uuid}")
        return data

    def save_yml(self, filename: str, editor: dict):
        """
        Save a file in server directory. This could easily be
        a method in the MinecraftServer class as a generic save_file
        method, but that will be done in the future.

        Args:
            filename (str): filename to save
            editor (nicegui editor): editor with content
        """
        if editor.content.get("json"):
            data = editor.content.get("json")
            try:
                with open(
                    os.path.join(self.server_path, filename), "w", encoding="utf-8"
                ) as file:
                    yaml.dump(data, file)

                setattr(self, FILE_TO_ATTR[filename], data)

            except Exception as e:
                logger.error(f"Error saving file: {e}")
                return False

        logger.info(f"Saved {filename} for server {self.uuid}")
        return True

    def load_paper_yml(self) -> dict:
        """
        Get paper.yml file as a dict
        """
        if self.has_paper_yml:
            self.paper_properties = self.load_yml("paper.yml")

    def load_spigot_yml(self) -> dict:
        """
        Get spigot.yml file as a dict
        """
        if self.has_spigot_yml:
            self.spigot_properties = self.load_yml("spigot.yml")
