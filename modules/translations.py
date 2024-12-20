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


def translate(message: str) -> str:
    """
    Returns corresponding translated message.
    If no translation is found, original message is returned
    """
    translated = translations.get(message, message)
    return translated
