"""The language can be changed while the app runs."""

from mcsc_gui.core import translations
from mcsc_gui.core.translations import current_language, set_language, translate


def test_set_language_changes_the_translations():
    assert translate("New server") == "New server"
    set_language("it")
    assert current_language() == "it"
    assert translate("New server") == "Nuovo server"
    set_language("en")
    assert current_language() == "en"
    assert translate("New server") == "New server"


def test_unknown_language_falls_back_to_english():
    set_language("it")
    set_language("xx")
    assert current_language() == "en"
    assert translate("New server") == "New server"


def test_placeholders_use_the_current_language():
    set_language("it")
    assert translate("1 server running") == "1 server in esecuzione"
    assert translations.languages_map[current_language()] == "Italiano"
