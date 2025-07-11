"""Settings"""

import os


# MISC APP SETTINGS
VERSION_FILENAME = "VERSION.txt"
GITHUB_REPO = "ddavidel/minecraft-server-creator"
UPDATE_BRANCH = "main"  # "main", "develop"
GITHUB_FILE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/refs/heads/{UPDATE_BRANCH}/{VERSION_FILENAME}"
BACKUP_DIR = "backups"

# DB
BACKEND = "json"
USER_SETTINGS_FILENAME = "user_settings.json"
USER_SETTINGS_PATH = os.path.join(os.getcwd(), "config")
USER_SETTINGS_FILE_PATH = os.path.join(USER_SETTINGS_PATH, USER_SETTINGS_FILENAME)

# TRANSLATION SETTINGS
DEFAULT_LANGUAGE = "en"  # user_settings.get("language", "en")
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
PAPER_VERSION_LIST_URL = "https://raw.githubusercontent.com/ddavidel/minecraft-server-jars/refs/heads/main/versions/paper_version_list.json"
