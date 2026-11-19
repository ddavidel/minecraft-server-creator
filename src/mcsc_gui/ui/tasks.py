"""
Long-running work from the UI: run it in the asyncio bridge, report it with toasts.

:func:`run_task` runs work in the bridge and reports it:
it never blocks the UI thread, shows an optional progress toast, disables
widgets meanwhile and calls back in the UI thread.
"""

from __future__ import annotations

import concurrent.futures
import logging
from collections.abc import Callable, Coroutine, Iterable
from typing import Any, TypeVar

from PySide6.QtWidgets import QWidget
from shiboken6 import isValid

from mcsc_gui.core.async_bridge import AsyncBridge
from mcsc_gui.core.server_manager import error_message
from mcsc_gui.ui.invoke import invoke_in_ui
from mcsc_gui.ui.widgets.toast import ToastHandle, ToastManager

logger = logging.getLogger(__name__)

T = TypeVar("T")

_bridge: AsyncBridge | None = None
_toasts: ToastManager | None = None


def configure(bridge: AsyncBridge, toasts: ToastManager | None) -> None:
    """Set the bridge and toast manager used by :func:`run_task`."""
    global _bridge, _toasts  # pylint: disable=global-statement
    _bridge, _toasts = bridge, toasts


def bridge() -> AsyncBridge:
    if _bridge is None:
        raise RuntimeError("ui.tasks is not configured")
    return _bridge


def toasts() -> ToastManager | None:
    return _toasts if _toasts is not None and isValid(_toasts) else None


def run_task(
    coro: Coroutine[Any, Any, T],
    *,
    progress: str | None = None,
    success: str | None = None,
    disable: Iterable[QWidget] = (),
    on_success: Callable[[T], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
    show_errors: bool = True,
) -> concurrent.futures.Future[T] | None:
    """Run ``coro`` in the bridge; callbacks run in the UI thread."""
    try:
        future = bridge().submit(coro)
    except RuntimeError as e:  # bridge stopped (app closing)
        logger.warning(f"Can't run task: {e}")
        return None
    _track(future, progress, success, list(disable), on_success, on_error, show_errors)
    return future


def run_blocking(
    fn: Callable[..., T],
    *args: Any,
    progress: str | None = None,
    success: str | None = None,
    disable: Iterable[QWidget] = (),
    on_success: Callable[[T], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
    show_errors: bool = True,
    **kwargs: Any,
) -> concurrent.futures.Future[T] | None:
    """Like :func:`run_task` for a blocking function (run in the bridge's executor)."""
    try:
        future = bridge().call(fn, *args, **kwargs)
    except RuntimeError as e:
        logger.warning(f"Can't run task: {e}")
        return None
    _track(future, progress, success, list(disable), on_success, on_error, show_errors)
    return future


def _safe_call(callback: Callable[[Any], None], value: Any) -> None:
    """Call a UI callback; its widgets may have been destroyed meanwhile (page left)."""
    try:
        callback(value)
    except RuntimeError as e:
        if "already deleted" not in str(e):
            raise
        logger.debug(f"Task callback skipped, widget deleted: {e}")


def _set_enabled(widgets: list[QWidget], enabled: bool) -> None:
    for widget in widgets:
        if isValid(widget):
            widget.setEnabled(enabled)


def _track(
    future: concurrent.futures.Future,
    progress: str | None,
    success: str | None,
    disable: list[QWidget],
    on_success: Callable[[Any], None] | None,
    on_error: Callable[[Exception], None] | None,
    show_errors: bool,
) -> None:
    _set_enabled(disable, False)
    manager = toasts()
    handle: ToastHandle | None = manager.progress(progress) if (progress and manager) else None

    def done() -> None:  # UI thread
        _set_enabled(disable, True)
        if future.cancelled():
            if handle is not None:
                handle.dismiss()
            return
        error = future.exception()
        if error is None:
            if handle is not None:
                if success:
                    handle.succeed(success)
                else:
                    handle.dismiss()
            elif success and toasts():
                toasts().success(success)
            if on_success is not None:
                _safe_call(on_success, future.result())
            return

        logger.error(f"Task failed ({progress or 'task'}): {error!r}")
        message = error_message(error)
        if handle is not None:
            handle.fail(message)
        elif show_errors and toasts():
            toasts().error(message)
        if on_error is not None and isinstance(error, Exception):
            _safe_call(on_error, error)

    future.add_done_callback(lambda _f: invoke_in_ui(done))


class ToastNotifier:
    """Core :class:`~mcsc_gui.core.notifier.Notifier` showing toasts. Callable from any thread."""

    def __init__(self, manager: ToastManager) -> None:
        self._manager = manager

    def _show(self, level: str, message: str) -> None:
        def show() -> None:
            if isValid(self._manager):
                getattr(self._manager, level)(message)

        invoke_in_ui(show)

    def info(self, message: str) -> None:
        self._show("info", message)

    def success(self, message: str) -> None:
        self._show("success", message)

    def error(self, message: str) -> None:
        self._show("error", message)
