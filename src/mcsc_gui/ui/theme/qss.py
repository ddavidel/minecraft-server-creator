"""
Global stylesheet generated from the design tokens ("Voxel" style).

Widgets pick a style through dynamic properties instead of ad-hoc stylesheets:

* ``QPushButton[variant="primary" | "secondary" | "danger" | "ghost" | "icon" | "nav"]``
* ``QLabel[role="display" | "headline" | "title" | "muted" | "caption" | "error"]``
* ``QFrame[card="true"]`` and ``QFrame[card="raised"]``

Blocks (buttons, cards) get a thicker, darker bottom border: pressing a button
shrinks it and moves the label down, so it looks pushed in.
"""

from __future__ import annotations

import tempfile
from functools import cache
from pathlib import Path

from mcsc_gui.ui.theme.tokens import TOKENS, Tokens

_CHECK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    '<path fill="none" stroke="{color}" stroke-width="4" stroke-linecap="square" '
    'stroke-linejoin="miter" d="M5 12.5l4.5 4.5L19 7.5"/></svg>'
)
_CHEVRON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    '<path fill="{color}" d="M6 9h12l-6 7z"/></svg>'
)


@cache
def _asset_dir() -> Path:
    """Folder for the small SVG assets QSS needs as files (check marks, arrows)."""
    path = Path(tempfile.gettempdir()) / "mcsc-qt-theme"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _asset(name: str, template: str, color: str) -> str:
    path = _asset_dir() / f"{name}-{color.strip('#')}.svg"
    if not path.exists():
        path.write_text(template.format(color=color), encoding="utf-8")
    return path.as_posix()


def build_stylesheet(t: Tokens = TOKENS) -> str:
    """The application-wide QSS."""
    p, r, s, ty, b = t.palette, t.radii, t.spacing, t.typography, t.borders
    check = _asset("check", _CHECK_SVG, p.text_on_accent)
    chevron = _asset("chevron", _CHEVRON_SVG, p.text_muted)
    h = t.control_height
    bw, bev = b.width, b.bevel
    # A pressed block: thinner bottom edge, label pushed down by the difference.
    push = bev - bw

    return f"""
* {{
    font-family: {ty.family};
    font-size: {ty.body}px;
    color: {p.text};
    outline: none;
}}
QWidget#Root, QWidget#Page, QStackedWidget#Pages {{
    background: {p.background};
}}
QToolTip {{
    background: {p.surface_raised};
    color: {p.text};
    border: {bw}px solid {p.border_strong};
    border-radius: {r.control}px;
    padding: 5px 8px;
    font-size: {ty.caption}px;
}}

/* ---------------------------------------------------------- typography */
QLabel[role="display"] {{ font-family: {ty.display_family}; font-size: {ty.display}px; font-weight: 700; }}
QLabel[role="headline"] {{ font-family: {ty.display_family}; font-size: {ty.headline}px; font-weight: 700; }}
QLabel[role="title"] {{ font-family: {ty.display_family}; font-size: {ty.title}px; font-weight: 700; }}
QLabel[role="muted"] {{ color: {p.text_muted}; }}
QLabel[role="caption"] {{ color: {p.text_muted}; font-size: {ty.caption}px; }}
QLabel[role="mono"] {{
    color: {p.text_muted}; font-family: {ty.mono_family}; font-size: {ty.caption}px;
}}
QLabel[role="error"] {{ color: {p.danger_text}; font-size: {ty.caption}px; }}
QLabel[role="warning"] {{ color: {p.warning_text}; }}
QLabel[role="overline"] {{
    font-family: {ty.display_family};
    color: {p.text_muted}; font-size: 13px; font-weight: 500;
    letter-spacing: 1px;
}}

/* --------------------------------------------------------------- cards */
QFrame[card="true"] {{
    background: {p.surface_raised};
    border: {bw}px solid {p.border};
    border-bottom: {b.card_bevel}px solid {p.surface_sunken};
    border-radius: {r.card}px;
}}
QFrame[card="raised"] {{
    background: {p.surface_hover};
    border: {bw}px solid {p.border_strong};
    border-bottom: {b.card_bevel}px solid {p.surface_sunken};
    border-radius: {r.card}px;
}}
QFrame[card="true"][clickable="true"]:hover {{
    border-color: {p.border_strong};
    border-bottom-color: {p.surface_sunken};
}}
QFrame[card="true"][clickable="true"]:focus {{
    border-color: {p.accent};
    border-bottom-color: {p.accent_shadow};
}}
QFrame#Sidebar {{
    background: {p.surface};
    border-right: {bw}px solid {p.surface_sunken};
}}
QFrame#TitleBar {{
    background: {p.surface};
    border-bottom: {bw}px solid {p.surface_sunken};
}}
QFrame#DialogPanel {{
    background: {p.background};
    border: {bw}px solid {p.border_strong};
    border-bottom: {b.card_bevel}px solid {p.surface_sunken};
    border-radius: {r.dialog}px;
}}
QFrame#Separator {{
    background: {p.border};
    max-height: {bw}px; min-height: {bw}px; border: none;
}}

/* ------------------------------------------------------------- buttons */
QPushButton {{
    min-height: {h - bw - bev}px;
    padding: 0 {s.lg}px;
    border-radius: {r.control}px;
    border: {bw}px solid {p.border_strong};
    border-bottom: {bev}px solid {p.surface_sunken};
    background: {p.surface_hover};
    font-weight: 600;
}}
QPushButton:hover {{ background: {p.border}; }}
QPushButton:pressed {{
    border-bottom-width: {bw}px;
    padding-top: {push}px;
    background: {p.surface_raised};
}}
QPushButton:focus {{ border-color: {p.accent}; border-bottom-color: {p.accent_shadow}; }}
QPushButton:disabled {{
    color: {p.text_disabled};
    background: {p.background};
    border: {bw}px solid {p.surface_hover};
    border-bottom: {bev}px solid {p.surface_hover};
}}
QPushButton[variant="primary"] {{
    background: {p.accent};
    border: {bw}px solid {p.accent};
    border-bottom: {bev}px solid {p.accent_shadow};
    color: {p.text_on_accent};
}}
QPushButton[variant="primary"]:hover {{
    background: {p.accent_hover}; border-color: {p.accent_hover};
    border-bottom-color: {p.accent_shadow};
}}
QPushButton[variant="primary"]:pressed {{
    background: {p.accent_pressed}; border-bottom-width: {bw}px; padding-top: {push}px;
}}
QPushButton[variant="primary"]:focus {{ border-color: {p.text}; border-bottom-color: {p.accent_shadow}; }}
QPushButton[variant="primary"]:disabled {{
    background: {p.accent_soft}; color: {p.text_disabled};
    border: {bw}px solid transparent; border-bottom: {bev}px solid transparent;
}}
QPushButton[variant="danger"] {{
    background: {p.danger};
    border: {bw}px solid {p.danger};
    border-bottom: {bev}px solid {p.danger_shadow};
    color: #ffffff;
}}
QPushButton[variant="danger"]:hover {{
    background: {p.danger_hover}; border-color: {p.danger_hover};
    border-bottom-color: {p.danger_shadow};
}}
QPushButton[variant="danger"]:pressed {{ border-bottom-width: {bw}px; padding-top: {push}px; }}
QPushButton[variant="danger"]:focus {{ border-color: {p.text}; border-bottom-color: {p.danger_shadow}; }}
QPushButton[variant="danger"]:disabled {{
    background: {p.danger_soft}; color: {p.text_disabled};
    border: {bw}px solid transparent; border-bottom: {bev}px solid transparent;
}}
QPushButton[variant="ghost"] {{
    background: transparent;
    border: {bw}px solid transparent;
    color: {p.text_muted};
}}
QPushButton[variant="ghost"]:hover {{ background: {p.surface_hover}; color: {p.text}; }}
QPushButton[variant="ghost"]:pressed {{ border-bottom-width: {bw}px; padding-top: {push}px; }}
QPushButton[variant="ghost"]:focus {{ border-color: {p.accent}; }}
QPushButton[variant="ghost"][tone="danger"] {{ color: {p.danger_text}; }}
QPushButton[variant="ghost"][tone="danger"]:hover {{ background: {p.danger_soft}; }}
QPushButton[variant="icon"] {{
    min-height: 30px; max-height: 30px; min-width: 30px; max-width: 30px;
    padding: 0;
    background: transparent;
    border: {bw}px solid transparent;
    border-radius: {r.control}px;
}}
QPushButton[variant="icon"]:hover {{ background: {p.surface_hover}; border-color: {p.border}; }}
QPushButton[variant="icon"]:pressed {{ background: {p.surface_sunken}; padding-top: {bw}px; }}
QPushButton[variant="icon"]:focus {{ border-color: {p.accent}; }}
QPushButton[variant="icon"]:disabled {{ background: transparent; border-color: transparent; }}
QPushButton[variant="window"] {{
    min-height: 26px; max-height: 26px; min-width: 32px; max-width: 32px;
    padding: 0; margin: 0 2px;
    border: {bw}px solid {p.border}; border-radius: {r.control}px;
    background: {p.surface_raised};
}}
QPushButton[variant="window"]:hover {{ background: {p.surface_hover}; border-color: {p.border_strong}; }}
QPushButton[variant="window"]:pressed {{ background: {p.surface_sunken}; padding-top: {bw}px; }}
QPushButton[variant="window"][tone="danger"] {{ border-color: #5a2a2d; background: #3a1d20; }}
QPushButton[variant="window"][tone="danger"]:hover {{ background: {p.danger}; border-color: {p.danger}; }}
QPushButton[variant="nav"] {{
    text-align: left;
    padding: 0 {s.md - bw}px;
    min-height: 36px;
    background: transparent;
    border: {bw}px solid transparent;
    color: {p.text_muted};
    font-weight: 500;
}}
QPushButton[variant="nav"]:hover {{ background: {p.surface_raised}; color: {p.text}; }}
QPushButton[variant="nav"]:pressed {{ padding-top: {bw}px; }}
QPushButton[variant="nav"]:checked {{
    background: {p.surface_raised}; border-color: {p.border};
    border-left: {bev}px solid {p.accent};
    color: {p.text}; font-weight: 600;
}}
QPushButton[variant="nav"]:focus {{ border-color: {p.accent}; }}
QPushButton[variant="nav"][highlight="true"] {{
    background: #2e2516; border-color: {p.warning_shadow}; color: {p.warning_text};
}}

/* -------------------------------------------------------------- inputs */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    min-height: {h - 2 * bw}px;
    padding: 0 {s.md - bw}px;
    background: {p.surface_sunken};
    border: {bw}px solid {p.border};
    border-radius: {r.control}px;
    selection-background-color: {p.accent};
    selection-color: {p.text_on_accent};
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: {p.border_strong};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {p.accent};
}}
QLineEdit:disabled, QComboBox:disabled {{
    color: {p.text_disabled}; background: {p.background}; border-color: {p.surface_hover};
}}
QLineEdit[invalid="true"] {{ border-color: {p.danger}; }}
QComboBox {{ padding-right: 28px; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox::down-arrow {{ image: url("{chevron}"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView, QListView#CompleterPopup {{
    background: {p.surface_raised};
    border: {bw}px solid {p.border_strong};
    border-radius: {r.control}px;
    padding: 2px;
    selection-background-color: {p.accent};
    selection-color: {p.text_on_accent};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}

QCheckBox {{ spacing: {s.sm + 2}px; }}
QCheckBox::indicator {{
    width: 14px; height: 14px;
    border-radius: 0;
    border: {bw}px solid {p.border_strong};
    background: {p.surface_sunken};
}}
QCheckBox::indicator:hover {{ border-color: {p.accent}; }}
QCheckBox::indicator:checked {{
    background: {p.accent};
    border-color: {p.accent_shadow};
    image: url("{check}");
}}
QCheckBox::indicator:disabled {{ border-color: {p.surface_hover}; background: {p.background}; }}
QCheckBox::indicator:checked:disabled {{ background: {p.accent_soft}; }}
QCheckBox:focus {{ color: {p.accent}; }}

QSlider::groove:horizontal {{
    height: 8px; border-radius: 0; background: {p.surface_sunken};
}}
QSlider::sub-page:horizontal {{ height: 8px; border-radius: 0; background: {p.accent}; }}
QSlider::handle:horizontal {{
    width: 12px; height: 20px; margin: -6px 0;
    border-radius: 0; background: {p.text}; border: {bw}px solid {p.surface_sunken};
}}
QSlider::handle:horizontal:hover {{ background: #ffffff; }}
QSlider:focus::handle:horizontal {{ border-color: {p.accent}; }}
QSlider::sub-page:horizontal:disabled {{ background: {p.text_disabled}; }}

QProgressBar {{
    min-height: 10px; max-height: 10px;
    background: {p.surface_sunken}; border: none; border-radius: 0;
    text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {p.accent}; width: 12px; margin-right: 3px; }}

/* ---------------------------------------------------- console & tables */
QPlainTextEdit#Console {{
    background: {p.console_background};
    border: {bw}px solid {p.border};
    border-radius: {r.control}px;
    padding: {s.sm}px;
    font-family: {ty.mono_family};
    font-size: 13px;
    selection-background-color: {p.accent};
    selection-color: {p.text_on_accent};
}}
QTableView, QTreeView {{
    background: {p.surface_raised};
    alternate-background-color: {p.surface_hover};
    border: {bw}px solid {p.border};
    border-radius: {r.control}px;
    gridline-color: {p.border};
    selection-background-color: {p.accent_soft};
    selection-color: {p.text};
}}
QTableView::item, QTreeView::item {{ padding: 4px 8px; min-height: 28px; }}
QHeaderView::section {{
    background: {p.surface};
    color: {p.text_muted};
    border: none;
    border-bottom: {bw}px solid {p.border};
    padding: 6px 8px;
    font-family: {ty.display_family};
    font-size: 13px;
    font-weight: 500;
}}
QTableCornerButton::section {{ background: {p.surface}; border: none; }}

/* ---------------------------------------------------------- scrollbars */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: {p.surface_sunken}; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: {p.surface_sunken}; height: 10px; margin: 0; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {p.border_strong}; border-radius: 0; min-height: 24px; min-width: 24px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background: {p.text_disabled};
}}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMenu {{
    background: {p.surface_raised};
    border: {bw}px solid {p.border_strong};
    border-radius: {r.control}px;
    padding: 2px;
}}
QMenu::item {{ padding: 6px 16px 6px 21px; border-radius: 0; }}
QMenu::icon {{ padding-left: 15px; }}
QMenu::item:selected {{ background: {p.accent}; color: {p.text_on_accent}; }}
QMenu::item:disabled {{ color: {p.text_disabled}; }}
QMenu::separator {{ height: {bw}px; background: {p.border_strong}; margin: 2px 0; }}
QWidget#DangerMenuItem {{ background: transparent; }}
QWidget#DangerMenuItem[active="true"] {{ background: {p.danger}; }}
QLabel#DangerMenuItemText {{ color: {p.danger_text}; background: transparent; }}
QLabel#DangerMenuItemText:disabled {{ color: {p.text_disabled}; }}
QWidget#DangerMenuItem[active="true"] QLabel#DangerMenuItemText {{ color: #ffffff; }}
QLabel#DangerMenuItemIcon {{ background: transparent; }}
"""
