"""Settings"""

import os
from modules.user_settings import user_settings


# MISC APP SETTINGS
VERSION_FILENAME = "VERSION.txt"
GITHUB_REPO = "ddavidel/minecraft-server-creator"
UPDATE_BRANCH = "main"  # "main", "develop"
GITHUB_FILE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/refs/heads/{UPDATE_BRANCH}/{VERSION_FILENAME}"
BACKUP_DIR = "backups"

# TRANSLATION SETTINGS
DEFAULT_LANGUAGE = user_settings.get("language", "en")
AVAILABLE_LANGAGUES = ["en", "it"]

# SERVERS SETTINGS
SERVERS_JSON_PATH = os.path.join(os.getcwd(), "config", "servers.json")
JAR_VERSIONS_FILTER = "stable"  # "stable", "none"
MAX_LOG_LINES = 300

# SERVER EXECUTION SETTINGS
JAVA_BIT_MODEL = "64"
NOGUI = True

# URLS
VANILLA_VERSION_LIST_URL = "https://raw.githubusercontent.com/ddavidel/minecraft-server-jars/refs/heads/main/versions/vanilla_version_list.json"
FORGE_VERSION_LIST_URL = "https://raw.githubusercontent.com/ddavidel/minecraft-forge-links/refs/heads/main/version_list.json"
SPIGOT_VERSION_LIST_URL = "https://raw.githubusercontent.com/ddavidel/minecraft-server-jars/refs/heads/main/versions/spigot_version_list.json"
