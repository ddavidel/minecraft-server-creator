"""
Bundled fonts (all SIL Open Font License).

Every ``.ttf``/``.otf`` in ``static/fonts`` is registered with Qt at startup, so
QSS can name the families (Pixelify Sans, IBM Plex Sans, IBM Plex Mono). Missing
files are not an error: the font stacks in :mod:`.tokens` fall back to system fonts.
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QFontDatabase

from mcsc_gui.utils import static_dir

logger = logging.getLogger(__name__)

FONT_SUFFIXES = (".ttf", ".otf")


def load_fonts() -> list[str]:
    """Register the bundled fonts; returns the font families now available."""
    folder = static_dir / "fonts"
    families: list[str] = []
    if not folder.is_dir():
        logger.info("No bundled fonts folder, using system fonts")
        return families

    for entry in sorted(folder.iterdir(), key=lambda e: e.name):
        if not entry.name.lower().endswith(FONT_SUFFIXES):
            continue
        font_id = QFontDatabase.addApplicationFontFromData(entry.read_bytes())
        if font_id < 0:
            logger.warning(f"Can't load font {entry.name}")
            continue
        families.extend(QFontDatabase.applicationFontFamilies(font_id))

    logger.info(f"Loaded fonts: {sorted(set(families))}")
    return sorted(set(families))
