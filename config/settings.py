"""Settings"""

import os


# MISC APP SETTINGS
VERSION_FILENAME = "VERSION.txt"
GITHUB_REPO = "ddavidel/minecraft-server-creator"
UPDATE_BRANCH = "main"  # "main", "develop"
GITHUB_FILE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/refs/heads/{UPDATE_BRANCH}/{VERSION_FILENAME}"
BACKUP_DIR = "backups"

# TRANSLATION SETTINGS
DEFAULT_LANGUAGE = "en"

# SERVERS SETTINGS
SERVERS_JSON_PATH = os.path.join(os.getcwd(), "config", "servers.json")
JAR_VERSIONS_FILTER = "stable"  # "stable", "none"
MAX_LOG_LINES = 300

# SERVER EXECUTION SETTINGS
JAVA_BIT_MODEL = "64"
NOGUI = True

# URLS
JAVA_VERSION_LIST_URL = "https://gist.githubusercontent.com/cliffano/77a982a7503669c3e1acb0a0cf6127e9/raw/a36b1e2f05ed3f1d1bbe9a7cf7fd3cfc7cb7a3a8/minecraft-server-jar-downloads.md"
FORGE_VERSION_LIST_URL = "https://raw.githubusercontent.com/ddavidel/minecraft-forge-links/refs/heads/main/version_list.json"
