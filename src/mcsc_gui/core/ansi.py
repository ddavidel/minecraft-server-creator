"""
ANSI escape sequences in the server output.

Paper and other servers color parts of their console output (command help,
join messages, plugins) with SGR sequences such as ``ESC[38;2;255;170;0m``
(24-bit), ``ESC[93m`` (16 colors) or ``ESC[38;5;208m`` (256 colors).
:func:`parse` splits a line into ``(text, style)`` runs for the console;
:func:`strip` removes every sequence for code that matches on the text.

No UI toolkit here: colors are ``#rrggbb`` strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

# Any CSI sequence (ESC [ params final-byte); only SGR ("m") changes the style
_CSI = re.compile(r"\x1b\[([0-9;:?]*)([@-~])")
# Other escapes (ESC, intermediate bytes, final byte: e.g. ESC(B charset) and a lone ESC
_OTHER_ESCAPE = re.compile(r"\x1b(?:[ -/]*[0-~]|$)")

# The 16 standard colors (30-37, 90-97), readable on the dark console
BASIC_COLORS = (
    "#4a4f5c",  # black: a dark grey, pure black would vanish on the console
    "#e05a5e",  # red
    "#5bbf3a",  # green
    "#e8b84a",  # yellow
    "#5a8fe8",  # blue
    "#c06ad8",  # magenta
    "#4fb3e8",  # cyan
    "#d8d6d0",  # white
)
BRIGHT_COLORS = (
    "#7a8090",  # bright black (grey)
    "#ff6b6e",  # bright red
    "#7ee05a",  # bright green
    "#ffe066",  # bright yellow
    "#7aa8ff",  # bright blue
    "#ff7cf0",  # bright magenta
    "#6ee6ff",  # bright cyan
    "#ffffff",  # bright white
)


@dataclass(frozen=True)
class Style:
    """Text attributes of a run (``color is None``: the console's default)."""

    color: str | None = None
    bold: bool = False
    italic: bool = False
    underline: bool = False


DEFAULT = Style()


def strip(line: str) -> str:
    """``line`` without any escape sequence."""
    if "\x1b" not in line:
        return line
    return _OTHER_ESCAPE.sub("", _CSI.sub("", line))


def _xterm_256(index: int) -> str | None:
    """Color of the 256-color palette (``ESC[38;5;n``)."""
    if not 0 <= index <= 255:
        return None
    if index < 8:
        return BASIC_COLORS[index]
    if index < 16:
        return BRIGHT_COLORS[index - 8]
    if index < 232:  # 6x6x6 cube
        index -= 16
        levels = (0, 95, 135, 175, 215, 255)
        r, g, b = levels[index // 36], levels[index // 6 % 6], levels[index % 6]
        return f"#{r:02x}{g:02x}{b:02x}"
    gray = 8 + (index - 232) * 10
    return f"#{gray:02x}{gray:02x}{gray:02x}"


def _extended_color(params: list[int], i: int) -> tuple[str | None, int]:
    """Color after a 38/48 at ``params[i]``; returns it and the index of the next code."""
    if i + 1 < len(params) and params[i + 1] == 5 and i + 2 < len(params):
        return _xterm_256(params[i + 2]), i + 3
    if i + 1 < len(params) and params[i + 1] == 2 and i + 4 < len(params):
        r, g, b = (max(0, min(255, v)) for v in params[i + 2:i + 5])
        return f"#{r:02x}{g:02x}{b:02x}", i + 5
    return None, len(params)  # malformed: ignore the rest of the sequence


def apply_sgr(style: Style, codes: str) -> Style:
    """The style after the SGR sequence ``ESC[<codes>m``."""
    params = [int(p) if p.isdigit() else 0 for p in re.split(r"[;:]", codes)] if codes else [0]
    i = 0
    while i < len(params):
        code = params[i]
        if code == 0:
            style = DEFAULT
        elif code == 1:
            style = replace(style, bold=True)
        elif code == 22:
            style = replace(style, bold=False)
        elif code == 3:
            style = replace(style, italic=True)
        elif code == 23:
            style = replace(style, italic=False)
        elif code == 4:
            style = replace(style, underline=True)
        elif code == 24:
            style = replace(style, underline=False)
        elif 30 <= code <= 37:
            style = replace(style, color=BASIC_COLORS[code - 30])
        elif 90 <= code <= 97:
            style = replace(style, color=BRIGHT_COLORS[code - 90])
        elif code == 39:
            style = replace(style, color=None)
        elif code in (38, 48):  # extended foreground / background (background ignored)
            color, i = _extended_color(params, i)
            if code == 38 and color is not None:
                style = replace(style, color=color)
            continue
        # Anything else (background colors, blink, ...) is ignored
        i += 1
    return style


def parse(line: str, style: Style = DEFAULT) -> list[tuple[str, Style]]:
    """Runs ``(text, style)`` of ``line``, starting from ``style``. Empty runs are dropped."""
    if "\x1b" not in line:
        return [(line, style)] if line else []
    runs: list[tuple[str, Style]] = []
    position = 0
    for match in _CSI.finditer(line):
        text = _OTHER_ESCAPE.sub("", line[position:match.start()])
        if text:
            runs.append((text, style))
        if match.group(2) == "m":
            style = apply_sgr(style, match.group(1))
        position = match.end()
    text = _OTHER_ESCAPE.sub("", line[position:])
    if text:
        runs.append((text, style))
    return runs
