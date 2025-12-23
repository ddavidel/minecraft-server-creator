"""Settings"""

import os
from appdirs import user_data_dir
from mcsc.modules.user_settings import UserSettings
_user_settings = UserSettings().user_settings

DEBUG=False
# MISC APP SETTINGS
VERSION_FILENAME = "VERSION.txt"
GITHUB_REPO = "ddavidel/minecraft-server-creator"
UPDATE_BRANCH = "main"  # "main", "develop"
GITHUB_FILE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/refs/heads/{UPDATE_BRANCH}/{VERSION_FILENAME}"
DATA_DIR_PATH = user_data_dir("mcsc")
BACKUP_DIR = os.path.join(DATA_DIR_PATH, "backups")
LOG_DIR_PATH = os.path.join(DATA_DIR_PATH, "logs")
TELEMETRY_DIR_PATH = os.path.join(DATA_DIR_PATH, "telemetry")
TELEMETRY_API = "https://mcscreator.altervista.org/telemetry/receiver.php"
PACKAGE_NAME = "minecraft-server-creator"
PYPI_PACKAGE_URL = f"https://pypi.org/pypi/{PACKAGE_NAME}/json"

# DB
BACKEND = "json"
USER_SETTINGS_FILENAME = "user_settings.json"
USER_SETTINGS_PATH = os.path.join(DATA_DIR_PATH, "config")
USER_SETTINGS_FILE_PATH = os.path.join(USER_SETTINGS_PATH, USER_SETTINGS_FILENAME)

# TRANSLATION SETTINGS
DEFAULT_LANGUAGE = _user_settings.get("language", "en")
AVAILABLE_LANGAGUES = ["en", "it"]

# SERVERS SETTINGS
SERVER_DIR_PATH = os.path.join(DATA_DIR_PATH, "servers")
SERVERS_JSON_PATH = os.path.join(DATA_DIR_PATH, "config", "servers.json")
JAR_VERSIONS_FILTER = "stable"  # "stable", "none"
MAX_LOG_LINES = 300

# SERVER EXECUTION SETTINGS
JAVA_BIT_MODEL = "64"
NOGUI = True

# URLS
VANILLA_VERSION_LIST_URL = "https://raw.githubusercontent.com/ddavidel/minecraft-server-jars/refs/heads/main/versions/vanilla_version_list.json"
FORGE_VERSION_LIST_URL = "https://raw.githubusercontent.com/ddavidel/minecraft-forge-links/refs/heads/main/version_list.json"
PAPER_VERSION_LIST_URL = "https://raw.githubusercontent.com/ddavidel/minecraft-server-jars/refs/heads/main/versions/paper_version_list.json"
