import json
from datetime import date
from pathlib import Path

import pytest

from mcsc_gui.core import changelog as cl


def entry(version, en=("Something new",), **extra):
    data = {"version": version, "date": "2026-11-21", "highlights": {"en": list(en)}}
    data.update(extra)
    return data


@pytest.mark.parametrize("value, expected", [
    ("3.1.0", (3, 1, 0)),
    ("v3.1.0", (3, 1, 0)),
    ("3.1.0.dev1", (3, 1, 0)),
    ("10.0.12", (10, 0, 12)),
    ("3.1", None),
    ("latest", None),
    ("", None),
    (None, None),
])
def test_parse_version(value, expected):
    assert cl.parse_version(value) == expected


def test_versions_compare_numerically():
    # The digit concatenation of check_for_updates would say 3.0.10 < 3.1.0 is false
    assert cl.parse_version("3.0.10") < cl.parse_version("3.1.0")


def test_parse_changelog_sorts_newest_first():
    notes = cl.parse_changelog({"releases": [entry("3.0.1"), entry("3.0.10"), entry("3.1.0")]})
    assert [n.version for n in notes] == ["3.1.0", "3.0.10", "3.0.1"]
    assert notes[0].date == date(2026, 11, 21)


def test_invalid_entries_are_skipped():
    notes = cl.parse_changelog({"releases": [
        entry("3.1.0"),
        entry("nope"),
        {"version": "3.0.5", "highlights": {"it": ["Solo italiano"]}},  # no English
        entry("3.0.4", date="yesterday"),
        entry("3.0.3", en=[]),
        "not an object",
    ]})
    assert [n.version for n in notes] == ["3.1.0"]


@pytest.mark.parametrize("data", [{}, [], {"releases": "x"}, None])
def test_malformed_document(data):
    assert cl.parse_changelog(data) == []


def test_read_missing_or_broken_file(tmp_path: Path):
    assert cl.read_changelog(tmp_path / "missing.json") == []
    broken = tmp_path / "broken.json"
    broken.write_text("{ not json", encoding="utf-8")
    assert cl.read_changelog(broken) == []


def test_language_fallback():
    note = cl.parse_entry(entry("3.1.0", en=["New"], title={"en": "Title"},
                                highlights={"en": ["New"], "it": ["Nuovo"]}))
    assert note.items("it") == ("Nuovo",)
    assert note.items("de") == ("New",)
    assert note.heading("it") == "Title"
    assert note.heading("en") == "Title"


def test_notes_between():
    notes = cl.parse_changelog({"releases": [entry(v) for v in
                                             ("3.0.0", "3.0.1", "3.1.0", "3.2.0")]})
    assert [n.version for n in cl.notes_between(notes, "3.0.0", "3.2.0")] == \
        ["3.2.0", "3.1.0", "3.0.1"]
    assert [n.version for n in cl.notes_between(notes, "3.1.0", "3.1.0")] == []
    assert [n.version for n in cl.notes_between(notes, None, "3.0.1")] == ["3.0.1", "3.0.0"]
    assert cl.notes_between(notes, "3.0.0", "dev") == []


def test_bundled_changelog_is_valid():
    """Every entry of the shipped file parses and has English highlights."""
    raw = json.loads(cl.get_static_path(cl.CHANGELOG_FILENAME).read_text(encoding="utf-8"))
    notes = cl.load_changelog()
    assert notes, "the bundled changelog is empty or invalid"
    assert len(notes) == len(raw["releases"]), "some bundled entries are invalid"
    assert len({n.version for n in notes}) == len(notes), "duplicated versions"
    for note in notes:
        assert note.items("en")
