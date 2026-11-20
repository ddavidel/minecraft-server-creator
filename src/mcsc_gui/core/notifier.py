"""
User notifications without a UI dependency.

The core reports problems through a :class:`Notifier`; the running UI registers
its own implementation with :func:`set_notifier`. Implementations must accept
calls from any thread (core code runs in the asyncio bridge thread).
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class Notifier(Protocol):
    """Something that can show a message to the user."""

    def info(self, message: str) -> None: ...

    def success(self, message: str) -> None: ...

    def error(self, message: str) -> None: ...

    # Optional: notifiers without ``warning`` get :meth:`error` (see :func:`notify_warning`).


class NullNotifier:
    """Default notifier: only logs. Used in tests and before the UI is ready."""

    def info(self, message: str) -> None:
        logger.info(message)

    def success(self, message: str) -> None:
        logger.info(message)

    def warning(self, message: str) -> None:
        logger.warning(message)

    def error(self, message: str) -> None:
        logger.error(message)


_notifier: Notifier = NullNotifier()


def set_notifier(notifier: Notifier | None) -> None:
    """Register the notifier used by the core (``None`` restores :class:`NullNotifier`)."""
    global _notifier  # pylint: disable=global-statement
    _notifier = notifier if notifier is not None else NullNotifier()


def get_notifier() -> Notifier:
    """The currently registered notifier."""
    return _notifier


def notify_warning(message: str) -> None:
    """Show a warning through the registered notifier (as an error if it has no ``warning``)."""
    notifier = get_notifier()
    getattr(notifier, "warning", notifier.error)(message)
