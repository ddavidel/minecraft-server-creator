"""Desktop shortcut: one-time startup prompt + shared creation task."""

from __future__ import annotations

import logging
import platform
from collections.abc import Callable, Iterable

from PySide6.QtWidgets import QWidget

from mcsc_gui.core import shortcuts
from mcsc_gui.core.translations import translate as _
from mcsc_gui.core.user_settings import UserSettings
from mcsc_gui.ui.tasks import run_blocking
from mcsc_gui.ui.widgets.overlay_dialog import MessageDialog

logger = logging.getLogger(__name__)

PROMPT_SETTING = "shortcut_prompt_shown"


def menu_name() -> str:
    return _("Start menu") if platform.system() == "Windows" else _("applications menu")


def mark_prompt_shown(settings: UserSettings) -> None:
    """Remember the prompt was dealt with: it never shows again."""
    if settings.user_settings.get(PROMPT_SETTING):
        return
    try:
        settings.update_settings(**{PROMPT_SETTING: True})
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Can't save the shortcut prompt flag")


def should_prompt(settings: UserSettings) -> bool:
    """True only the first time, and only if there's no desktop shortcut yet."""
    if not shortcuts.is_supported() or settings.user_settings.get(PROMPT_SETTING):
        return False
    if shortcuts.desktop_shortcut_exists():
        mark_prompt_shown(settings)
        return False
    return True


def create_shortcuts(*, settings: UserSettings | None = None, disable: Iterable[QWidget] = (),
                     on_success: Callable[[list], None] | None = None):
    """Create desktop + menu shortcuts in the background, with progress/result toasts."""

    def done(paths: list) -> None:
        mark_prompt_shown(settings or UserSettings())
        if on_success is not None:
            on_success(paths)

    return run_blocking(
        shortcuts.create_shortcuts,
        progress=_("Creating shortcut"),
        success=_("Shortcut added to the desktop and the {menu}", menu=menu_name()),
        disable=disable, on_success=done,
    )


class ShortcutPromptDialog(MessageDialog):
    """Asked once at startup: "add MCSC to the desktop?"."""

    def __init__(self, parent: QWidget, settings: UserSettings | None = None) -> None:
        super().__init__(
            parent, _("Add a desktop shortcut?"),
            _("Do you want to add a Minecraft Server Creator shortcut to your desktop "
              "and to the {menu}? You can also do it later from the app settings.",
              menu=menu_name()),
            confirm=_("Yes, add it"), cancel=_("No, thanks"),
            confirm_icon="shortcut",
        )
        self._settings = settings
        self.accepted.connect(lambda: create_shortcuts(settings=self._settings))
