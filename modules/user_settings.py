"""
User settings module
"""

import os
import json


USER_SETTINGS_PATH = os.path.join(os.getcwd(), "config", "user_settings.json")


def load_custom_settings():
    """
    Loads the user settings json. If the file does not exist, it is created.
    """
    if not os.path.exists(USER_SETTINGS_PATH):
        with open(USER_SETTINGS_PATH, "w", encoding="utf-8") as file:
            file.write("{}")
            file.flush()
        return {}

    with open(USER_SETTINGS_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


user_settings = load_custom_settings()


def save_custom_settings():
    """Saves the user settings json"""
    with open(USER_SETTINGS_PATH, "w", encoding="utf-8") as file:
        json.dump(user_settings, file, indent=4)
        file.flush()


def update_settings(settings_dict: dict = None, **kwargs):
    """Updates the user settings json"""
    if settings_dict:
        if not isinstance(settings_dict, dict):
            raise ValueError("settings_dict must be a dictionary")

        if user_settings.keys() != settings_dict.keys():
            raise ValueError(
                "settings_dict must have the same keys as the user_settings"
            )

        user_settings.update(settings_dict)

    else:
        initial_settings = user_settings.copy()
        for key, value in kwargs.items():
            if key not in user_settings.keys():
                user_settings.update(initial_settings)
                raise ValueError(f"Invalid setting: {key}")

            user_settings[key] = value

    # Save settings
    save_custom_settings()
