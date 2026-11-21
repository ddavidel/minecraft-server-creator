"""
User settings module
"""

import os
import json
import logging
from appdirs import user_data_dir


logger = logging.getLogger(__name__)

USER_SETTINGS_PATH = os.path.join(user_data_dir("mcsc"), "config", "user_settings.json")


# shortcut_prompt_shown: the "add a desktop shortcut?" popup was already shown once
# auto_backup: app-wide automatic backup policy (see AUTO_BACKUP_POLICIES)
# backup_retention: automatic backups kept per server (0 = unlimited)
# last_seen_version: the last version whose "What's New" notes were shown
# start_with_os: start the app (in the tray) at login; see mcsc_gui.core.autostart
# close_to_tray: closing the window hides it in the system tray instead of quitting
# tray_hint_shown: the "still running in the tray" notification was already shown once
KNOWN_SETTINGS = [
    "language", "native_title_bar", "shortcut_prompt_shown", "auto_backup", "backup_retention",
    "last_seen_version", "start_with_os", "close_to_tray", "tray_hint_shown",
]

# Use the OS title bar unless the user opts into the custom one
DEFAULT_NATIVE_TITLE_BAR = True

# Automatic backups: when a server is backed up without the user asking
AUTO_BACKUP_POLICIES = ("never", "on_start", "on_stop")
DEFAULT_AUTO_BACKUP = "never"
DEFAULT_BACKUP_RETENTION = 5

# Closing the window keeps the app (and its servers) running in the tray
DEFAULT_CLOSE_TO_TRAY = True


def _to_bool(value) -> bool:
    """Bool conversion that also understands the strings "true"/"false"."""
    if isinstance(value, str):
        if value.strip().lower() in {"1", "true", "yes", "on"}:
            return True
        if value.strip().lower() in {"0", "false", "no", "off", ""}:
            return False
        raise ValueError(f"Not a boolean: {value!r}")
    return bool(value)


def _to_policy(value) -> str:
    """An automatic backup policy (one of :data:`AUTO_BACKUP_POLICIES`)."""
    value = str(value).strip().lower()
    if value not in AUTO_BACKUP_POLICIES:
        raise ValueError(f"Not a backup policy: {value!r}")
    return value


def _to_retention(value) -> int:
    """A non negative number of backups to keep (0 = unlimited)."""
    value = int(value)
    if value < 0:
        raise ValueError(f"Retention can't be negative: {value}")
    return value


TYPES_CONVERTION = {
    "language": str,
    "native_title_bar": _to_bool,
    "shortcut_prompt_shown": _to_bool,
    "auto_backup": _to_policy,
    "backup_retention": _to_retention,
    "last_seen_version": str,
    "start_with_os": _to_bool,
    "close_to_tray": _to_bool,
    "tray_hint_shown": _to_bool,
}


# def load_custom_settings():
#     """
#     Loads the user settings json. If the file does not exist, it is created.
#     """
#     if not os.path.exists(USER_SETTINGS_PATH):
#         os.makedirs(os.path.dirname(USER_SETTINGS_PATH), exist_ok=True)
#         with open(USER_SETTINGS_PATH, "w", encoding="utf-8") as file:
#             file.write("{}")
#             file.flush()
#         return {}

#     with open(USER_SETTINGS_PATH, "r", encoding="utf-8") as file:
#         return json.load(file)

#     logger.info("Loaded user settings")


# user_settings = load_custom_settings()


# def save_custom_settings():
#     """Saves the user settings json"""
#     with open(USER_SETTINGS_PATH, "w", encoding="utf-8") as file:
#         json.dump(user_settings, file, indent=4)
#         file.flush()
#     logger.info("Saved user settings")


# def update_settings(settings_dict: dict = None, **kwargs):
#     """Updates the user settings json"""
#     logger.info(f"Updating user settings: {settings_dict or kwargs}")
#     if settings_dict:
#         if not isinstance(settings_dict, dict):
#             raise ValueError("settings_dict must be a dictionary")

#         if user_settings.keys() != settings_dict.keys():
#             raise ValueError(
#                 "settings_dict must have the same keys as the user_settings"
#             )

#         user_settings.update(settings_dict)

#     else:
#         initial_settings = user_settings.copy()
#         for key, value in kwargs.items():
#             if key not in user_settings.keys() and key not in KNOWN_SETTINGS:
#                 user_settings.update(initial_settings)
#                 raise ValueError(f"Invalid setting: {key}")

#             try:
#                 user_settings[key] = TYPES_CONVERTION[key](value)
#             except ValueError as e:
#                 user_settings.update(initial_settings)
#                 save_custom_settings()
#                 raise ValueError(f"Invalid value for setting {key}: {value}") from e

#     # Save settings
#     save_custom_settings()


class UserSettings:
    """User settings"""
    language = "en"  # default
    user_settings = {}

    def __init__(self):
        self.user_settings = self.load_custom_settings()

    def load_custom_settings(self) -> dict:
        """
        Loads the user settings json. If the file does not exist, it is created.
        """
        if not os.path.exists(USER_SETTINGS_PATH):
            os.makedirs(os.path.dirname(USER_SETTINGS_PATH), exist_ok=True)
            with open(USER_SETTINGS_PATH, "w", encoding="utf-8") as file:
                file.write("{}")
                file.flush()
            return {}

        with open(USER_SETTINGS_PATH, "r", encoding="utf-8") as file:
            return json.load(file)

    def save_custom_settings(self):
        """Saves the user settings json"""
        with open(USER_SETTINGS_PATH, "w", encoding="utf-8") as file:
            json.dump(self.user_settings, file, indent=4)
            file.flush()
        logger.info("Saved user settings")

    def update_settings(self, settings_dict: dict = None, **kwargs):
        """Updates the user settings json"""
        logger.info(f"Updating user settings: {settings_dict or kwargs}")
        if settings_dict:
            if not isinstance(settings_dict, dict):
                raise ValueError("settings_dict must be a dictionary")

            if self.user_settings.keys() != settings_dict.keys():
                raise ValueError(
                    "settings_dict must have the same keys as the user_settings"
                )

            self.user_settings.update(settings_dict)

        else:
            initial_settings = self.user_settings.copy()
            for key, value in kwargs.items():
                if key not in self.user_settings.keys() and key not in KNOWN_SETTINGS:
                    self.user_settings.update(initial_settings)
                    raise ValueError(f"Invalid setting: {key}")

                try:
                    self.user_settings[key] = TYPES_CONVERTION[key](value)
                except ValueError as e:
                    self.user_settings.update(initial_settings)
                    self.save_custom_settings()
                    raise ValueError(f"Invalid value for setting {key}: {value}") from e

        # Save settings
        self.save_custom_settings()
