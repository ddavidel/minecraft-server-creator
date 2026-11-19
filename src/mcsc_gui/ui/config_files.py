"""Editable server config files shown in the detail page."""

from __future__ import annotations

from mcsc import MinecraftServer

from mcsc_gui.core.server_manager import config_file_exists
from mcsc_gui.core.translations import translate as _

# Labels of the editor buttons for well known config files
CONFIG_FILE_LABELS = {
    "server.properties": "Edit server properties",
    "spigot.yml": "Edit spigot properties",
    "paper.yml": "Edit paper properties",
    "config/paper-global.yml": "Edit paper properties",
    "bukkit.yml": "Edit bukkit properties",
    "config/paper-world-defaults.yml": "Edit paper world defaults",
}


def config_file_label(filename: str) -> str:
    return _(CONFIG_FILE_LABELS.get(filename, "Edit {file}"), file=filename)


def visible_config_files(server: MinecraftServer) -> list[tuple[str, bool]]:
    """``(filename, enabled)`` for the editor buttons.

    ``server.properties`` is generated on the first start: it's shown disabled
    until then. The other files are shown only if they exist.
    """
    files = []
    for filename in server.CONFIG_FILES:
        exists = config_file_exists(server, filename)
        if filename != "server.properties" and not exists:
            continue
        files.append((filename, exists))
    return files
