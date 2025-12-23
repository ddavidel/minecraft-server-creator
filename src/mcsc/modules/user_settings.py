"""
User settings module
"""

import os
import json
from appdirs import user_data_dir


USER_SETTINGS_PATH = os.path.join(user_data_dir("mcsc"), "config", "user_settings.json")


KNOWN_SETTINGS = ["language"]

TYPES_CONVERTION = {
    "language": str,
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
        # pylint: disable=import-outside-toplevel
        from mcsc.modules.logger import RotatingLogger
        logger = RotatingLogger()
        with open(USER_SETTINGS_PATH, "w", encoding="utf-8") as file:
            json.dump(self.user_settings, file, indent=4)
            file.flush()
        logger.info("Saved user settings")

    def update_settings(self, settings_dict: dict = None, **kwargs):
        """Updates the user settings json"""
        # pylint: disable=import-outside-toplevel
        from mcsc.modules.logger import RotatingLogger
        logger = RotatingLogger()
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
