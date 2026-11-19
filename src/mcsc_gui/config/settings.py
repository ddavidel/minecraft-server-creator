"""Settings"""

import os
from appdirs import user_data_dir
from mcsc_gui.core.user_settings import UserSettings
_user_settings = UserSettings().user_settings

DEBUG = os.environ.get("MCSC_DEBUG", "").lower() in {"1", "true", "yes"}
# MISC APP SETTINGS
# The data folder keeps the historical "mcsc" name so existing installs keep their data
DATA_DIR_PATH = user_data_dir("mcsc")
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

# SERVERS SETTINGS (server management is handled by the pymcsc library)
SERVER_DIR_PATH = os.path.join(DATA_DIR_PATH, "servers")
SERVERS_JSON_PATH = os.path.join(DATA_DIR_PATH, "config", "servers.json")
JAR_VERSIONS_FILTER = "stable"  # "stable", "none"
MAX_LOG_LINES = 300
SERVER_STOP_TIMEOUT = 60  # seconds before a server that doesn't stop gets killed
