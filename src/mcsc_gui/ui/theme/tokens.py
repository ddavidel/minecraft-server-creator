"""
Design tokens: the single source of truth for the look of the app (FR-027).

Widgets never hard-code colors or sizes: they read them from :data:`TOKENS`, and
the global stylesheet is generated from them (see :mod:`.qss`). A light theme
would be another :class:`Palette` instance.

Style "Voxel": square corners, chunky 2 px borders and a darker bottom edge
(``*_shadow`` colors) that makes buttons and cards look like pressable blocks.
Headings use a pixel font, body text a plain sans.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Palette:
    """Colors (hex or rgba strings understood by both QSS and QColor)."""

    background: str = "#1c1f26"
    surface: str = "#16181e"          # sidebar, title bar, inset panels
    surface_raised: str = "#232733"   # cards, tiles, toasts
    surface_hover: str = "#2b303c"
    surface_sunken: str = "#12141a"   # inputs, empty segments, bevel edge
    border: str = "#343a4a"
    border_strong: str = "#4a5060"
    overlay: str = "rgba(8, 9, 12, 170)"

    text: str = "#f0ede6"
    text_muted: str = "#a39f95"
    text_disabled: str = "#5f6370"
    text_on_accent: str = "#0f1a0a"

    accent: str = "#5bbf3a"           # grass
    accent_hover: str = "#6bcc4a"
    accent_pressed: str = "#4fa832"
    accent_shadow: str = "#2f6e1b"    # bottom edge of accent blocks
    accent_soft: str = "rgba(91, 191, 58, 46)"

    danger: str = "#cf3438"
    danger_hover: str = "#db4448"
    danger_shadow: str = "#8f2a2d"
    danger_text: str = "#ff8a8d"
    danger_soft: str = "rgba(207, 52, 56, 46)"
    warning: str = "#ffaa33"
    warning_text: str = "#ffc46b"
    warning_shadow: str = "#5c4320"
    warning_soft: str = "rgba(255, 170, 51, 38)"
    info: str = "#4fb3e8"
    success: str = "#5bbf3a"
    dirt: str = "#9c6b3f"             # secondary decorative color

    console_background: str = "#0b0c0f"


@dataclass(frozen=True)
class Radii:
    card: int = 2
    dialog: int = 2
    control: int = 2
    pill: int = 2


@dataclass(frozen=True)
class Borders:
    width: int = 2       # every outline
    bevel: int = 4       # bottom edge of buttons
    card_bevel: int = 6  # bottom edge of cards


@dataclass(frozen=True)
class Spacing:
    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 24
    xxl: int = 32


@dataclass(frozen=True)
class Typography:
    # Bundled in static/fonts (OFL), with system fallbacks if missing.
    display_family: str = '"Pixelify Sans", "IBM Plex Sans", "Segoe UI", sans-serif'
    family: str = '"IBM Plex Sans", "Segoe UI Variable Text", "Segoe UI", sans-serif'
    mono_family: str = '"IBM Plex Mono", "Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace'
    # Scale (px): caption, body, title, headline, display
    caption: int = 12
    body: int = 14
    title: int = 18
    headline: int = 28
    display: int = 34


@dataclass(frozen=True)
class Motion:
    fast_ms: int = 150
    normal_ms: int = 180
    slow_ms: int = 200


@dataclass(frozen=True)
class Tokens:
    palette: Palette = field(default_factory=Palette)
    radii: Radii = field(default_factory=Radii)
    borders: Borders = field(default_factory=Borders)
    spacing: Spacing = field(default_factory=Spacing)
    typography: Typography = field(default_factory=Typography)
    motion: Motion = field(default_factory=Motion)

    sidebar_width: int = 232
    title_bar_height: int = 44
    control_height: int = 38


TOKENS = Tokens()
