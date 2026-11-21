"""
Long-running work from the UI: run it in the asyncio bridge, report it with toasts.

:func:`run_task` runs work in the bridge and reports it:
it never blocks the UI thread, shows an optional progress toast, disables
widgets meanwhile and calls back in the UI thread.
"""

from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
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


class FileProgress:
    """``(done, total)`` progress callback that updates the task's progress toast.

    Pass it to the work (it may be called from any thread) and to
    :func:`run_task` as ``tracker``; updates are throttled.
    """

    INTERVAL = 0.2  # seconds between toast updates

    def __init__(self, text: str) -> None:
        self.text = text
        self._handle: ToastHandle | None = None
        self._lock = threading.Lock()
        self._last = 0.0
        self.done = 0
        self.total = 0

    def attach(self, handle: ToastHandle | None) -> None:
        self._handle = handle

    def message(self) -> str:
        if not self.total:
            return self.text
        return f"{self.text} ({self.done}/{self.total})"

    def __call__(self, done: int, total: int) -> None:
        with self._lock:
            self.done, self.total = done, total
            now = time.monotonic()
            if done < total and now - self._last < self.INTERVAL:
                return
            self._last = now
        handle = self._handle
        if handle is not None:
            message = self.message()
            invoke_in_ui(lambda: handle.update(message))


def run_task(
    coro: Coroutine[Any, Any, T],
    *,
    progress: str | None = None,
    success: str | None = None,
    disable: Iterable[QWidget] = (),
    on_success: Callable[[T], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
    show_errors: bool = True,
    tracker: FileProgress | None = None,
) -> concurrent.futures.Future[T] | None:
    """Run ``coro`` in the bridge; callbacks run in the UI thread.

    ``tracker`` (also passed to the work) shows its progress in the toast.
    """
    try:
        future = bridge().submit(coro)
    except RuntimeError as e:  # bridge stopped (app closing)
        logger.warning(f"Can't run task: {e}")
        coro.close()
        return None
    _track(future, progress, success, list(disable), on_success, on_error, show_errors, tracker)
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
    tracker: FileProgress | None = None,
) -> None:
    _set_enabled(disable, False)
    manager = toasts()
    handle: ToastHandle | None = manager.progress(progress) if (progress and manager) else None
    if tracker is not None:
        tracker.attach(handle)

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

    def warning(self, message: str) -> None:
        self._show("warning", message)

    def error(self, message: str) -> None:
        self._show("error", message)
