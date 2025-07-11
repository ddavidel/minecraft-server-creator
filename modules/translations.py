"""
Translations module
"""

import importlib

# from config.settings import DEFAULT_LANGUAGE
from modules.user_settings import get_db


languages_map = {
    "en": "English",
    "it": "Italiano",
}


def load_language():
    """
    Loads the language module based on the DEFAULT_LANGUAGE setting.
    If the module is not found, an empty dictionary is returned.
    """
    db = get_db()
    if db.exists("language"):
        lang = db.get("language")
    else:
        lang = "en"
    try:
        return importlib.import_module(f"localization.{lang}").translations

    except ImportError:
        return {}


translations = load_language()


def translate(message: str, **kwargs) -> str:
    """
    Returns the corresponding translated message with placeholders replaced.
    If no translation is found, the original message is returned.
    """
    translated = translations.get(message, message)

    try:
        return translated.format(**kwargs)

    except KeyError as e:
        print(f"Warning: Missing placeholder key {e} for message: {message}")
        raise

    except ValueError as e:
        print(f"Error: Invalid format in message: {message}. Error: {e}")
        raise


def reload_translations():
    """Reloads the translations dict. Use this after updating language setting"""
    global translations  # pylint: disable=global-statement
    translations = load_language()
