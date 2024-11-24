"""Settings"""
import os


# SERVERS SETTINGS
SERVERS_JSON_PATH = os.path.join(os.getcwd(), "config", "servers.json")
JAR_VERSIONS_FILTER = "stable"
MAX_LOG_LINES = 300

# SERVER EXECUTION SETTINGS
JAVA_BIT_MODEL = "64"
NOGUI = True
