"""
Translations module
"""

import importlib

from config.settings import DEFAULT_LANGUAGE


try:
    translations = importlib.import_module(
        f"localization.{DEFAULT_LANGUAGE}"
    ).translations
except ImportError:
    translations = {}


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
