"""Settings"""

import os


# SERVERS SETTINGS
SERVERS_JSON_PATH = os.path.join(os.getcwd(), "config", "servers.json")
JAR_VERSIONS_FILTER = "stable"  # "stable", "none"
MAX_LOG_LINES = 300

# SERVER EXECUTION SETTINGS
JAVA_BIT_MODEL = "64"
NOGUI = True

# URLS
VERSION_LIST_URL = "https://gist.githubusercontent.com/cliffano/77a982a7503669c3e1acb0a0cf6127e9/raw/a36b1e2f05ed3f1d1bbe9a7cf7fd3cfc7cb7a3a8/minecraft-server-jar-downloads.md"
