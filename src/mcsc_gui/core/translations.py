"""
Translations module

The active language is module state: it starts from the user setting and can be
changed at runtime with :func:`set_language`. :func:`translate` always reads the
current language, but texts already shown by widgets don't change by themselves:
the main window rebuilds its UI after a change (see ``MainWindow.apply_settings``).
"""

import importlib
import logging

from mcsc_gui.config.settings import AVAILABLE_LANGAGUES, DEFAULT_LANGUAGE

logger = logging.getLogger(__name__)

# The language of the source strings: it has no translation module
SOURCE_LANGUAGE = "en"

languages_map = {
    "en": "English",
    "it": "Italiano",
}

_language = SOURCE_LANGUAGE
_translations: dict[str, str] = {}


def _load(language: str) -> dict[str, str]:
    """The translations of ``language`` (empty for English or an unknown language)."""
    if language == SOURCE_LANGUAGE:
        return {}
    try:
        return importlib.import_module(f"mcsc_gui.localization.{language}").translations
    except ImportError:
        logger.warning(f"No translations for language {language!r}")
        return {}


def set_language(language: str) -> None:
    """Use ``language`` from now on (an unknown one falls back to English)."""
    global _language, _translations  # pylint: disable=global-statement
    if language not in AVAILABLE_LANGAGUES:
        logger.warning(f"Unknown language {language!r}: using {SOURCE_LANGUAGE!r}")
        language = SOURCE_LANGUAGE
    _translations = _load(language)
    _language = language


def current_language() -> str:
    """The code of the active language (e.g. ``"it"``)."""
    return _language


def translate(message: str, **kwargs) -> str:
    """
    Returns the corresponding translated message with placeholders replaced.
    If no translation is found, the original message is returned.
    """
    translated = _translations.get(message, message)

    try:
        return translated.format(**kwargs)

    except KeyError as e:
        print(f"Warning: Missing placeholder key {e} for message: {message}")
        raise

    except ValueError as e:
        print(f"Error: Invalid format in message: {message}. Error: {e}")
        raise


set_language(DEFAULT_LANGUAGE)
