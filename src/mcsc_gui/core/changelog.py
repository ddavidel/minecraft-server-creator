"""
Release notes ("What's New").

The notes ship with the app in ``static/changelog.json`` (no network needed):
one entry per release, newest first, with the highlights in each language.
They're written once per release, from the draft made by
``scripts/draft_changelog.py``.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

from mcsc_gui.utils import get_static_path

logger = logging.getLogger(__name__)

CHANGELOG_FILENAME = "changelog.json"
FALLBACK_LANGUAGE = "en"

_VERSION_RE = re.compile(r"^\s*v?(\d+)\.(\d+)\.(\d+)")

Version = tuple[int, int, int]


def parse_version(value) -> Version | None:
    """``"v3.1.0"`` / ``"3.1.0.dev1"`` -> ``(3, 1, 0)``; anything else -> None."""
    if not isinstance(value, str):
        return None
    match = _VERSION_RE.match(value)
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


@dataclass(frozen=True)
class ReleaseNote:
    """The notes of one release."""

    version: str
    date: date | None
    highlights: dict[str, tuple[str, ...]]
    title: dict[str, str] = field(default_factory=dict)

    @property
    def key(self) -> Version:
        return parse_version(self.version) or (0, 0, 0)

    def items(self, language: str) -> tuple[str, ...]:
        """The highlights in ``language``, in English if it has none."""
        return self.highlights.get(language) or self.highlights.get(FALLBACK_LANGUAGE, ())

    def heading(self, language: str) -> str:
        """The title in ``language`` (English fallback), or ``""``."""
        return self.title.get(language) or self.title.get(FALLBACK_LANGUAGE, "")


def _texts(value, name: str) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, dict):
        raise ValueError(f"'{name}' must be an object")
    result = {}
    for language, items in value.items():
        if not isinstance(items, list) or not all(isinstance(i, str) and i.strip() for i in items):
            raise ValueError(f"'{name}.{language}' must be a list of strings")
        result[str(language)] = tuple(i.strip() for i in items)
    return result


def parse_entry(entry) -> ReleaseNote:
    """A :class:`ReleaseNote` from a ``releases`` item; ValueError if it's invalid."""
    if not isinstance(entry, dict):
        raise ValueError("an entry must be an object")
    version = entry.get("version")
    if parse_version(version) is None:
        raise ValueError(f"invalid version: {version!r}")
    raw_date = entry.get("date")
    try:
        day = date.fromisoformat(raw_date) if raw_date else None
    except (TypeError, ValueError) as e:
        raise ValueError(f"invalid date: {raw_date!r}") from e
    highlights = _texts(entry.get("highlights"), "highlights")
    if not highlights.get(FALLBACK_LANGUAGE):
        raise ValueError(f"no '{FALLBACK_LANGUAGE}' highlights")
    title = entry.get("title") or {}
    if not isinstance(title, dict) or not all(isinstance(t, str) for t in title.values()):
        raise ValueError("'title' must be an object of strings")
    return ReleaseNote(version.strip().lstrip("v"), day, highlights, dict(title))


def parse_changelog(data) -> list[ReleaseNote]:
    """The valid entries of a changelog document, newest first (invalid ones are skipped)."""
    releases = data.get("releases") if isinstance(data, dict) else None
    if not isinstance(releases, list):
        logger.warning("Changelog without a 'releases' list")
        return []
    notes = []
    for entry in releases:
        try:
            notes.append(parse_entry(entry))
        except ValueError as e:
            logger.warning(f"Skipping invalid changelog entry: {e}")
    notes.sort(key=lambda note: note.key, reverse=True)
    return notes


def read_changelog(path: str | Path | None = None) -> list[ReleaseNote]:
    """Load the notes from ``path`` (the bundled file by default). Never raises."""
    try:
        source = Path(path) if path is not None else get_static_path(CHANGELOG_FILENAME)
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning(f"Can't read the changelog: {e}")
        return []
    return parse_changelog(data)


@lru_cache(maxsize=1)
def _bundled() -> tuple[ReleaseNote, ...]:
    return tuple(read_changelog())


def load_changelog() -> list[ReleaseNote]:
    """The bundled release notes, newest first (read once)."""
    return list(_bundled())


def notes_between(notes, after: str | None, up_to: str) -> list[ReleaseNote]:
    """Notes of the releases newer than ``after`` (None = all) up to ``up_to`` included."""
    top = parse_version(up_to)
    if top is None:
        return []
    bottom = parse_version(after) if after else None
    return [note for note in notes
            if note.key <= top and (bottom is None or note.key > bottom)]
