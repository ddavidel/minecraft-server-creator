"""
User settings module
"""

import os
import json

from ddevdb import Database

from modules.logger import RotatingLogger
from config.settings import USER_SETTINGS_FILE_PATH, BACKEND


logger = RotatingLogger()

KNOWN_SETTINGS = ["language"]

TYPES_CONVERTION = {
    "language": str,
}


def get_db() -> Database:
    """Returns a ddevdb Database instance"""
    db = Database(
        # filename=USER_SETTINGS_FILENAME,  # kinda counter intuitive
        filepath=USER_SETTINGS_FILE_PATH,
        backend=BACKEND,
    )
    return db


def get_custom_settings() -> dict:
    """
    Loads the user settings json.
    """
    db = get_db()
    return db.get()


user_settings = get_custom_settings()


def save_custom_settings():
    """Saves the user settings json"""
    with open(USER_SETTINGS_FILE_PATH, "w", encoding="utf-8") as file:
        json.dump(user_settings, file, indent=4)
        file.flush()
    logger.info("Saved user settings")


def update_settings(settings_dict: dict = None, **kwargs):
    """Updates the user settings json"""
    logger.info(f"Updating user settings: {settings_dict or kwargs}")
    db = get_db()
    # I suggest rewriting all of this

    for setting, value in kwargs.items():
        if setting not in KNOWN_SETTINGS:
            raise ValueError(f"Invalid setting: {setting}")

        try:
            converted_value = TYPES_CONVERTION[setting](value)
        except ValueError as e:
            raise ValueError(f"Invalid value for setting {setting}: {value}") from e

        # Update setting
        db[setting] = converted_value

    # No clue if this will ever be useful
    # if settings_dict:
    #     if not isinstance(settings_dict, dict):
    #         raise ValueError("settings_dict must be a dictionary")

    #     if user_settings.keys() != settings_dict.keys():
    #         raise ValueError(
    #             "settings_dict must have the same keys as the user_settings"
    #         )

    #     user_settings.update(settings_dict)
