"""
Run code in the Qt UI thread from any thread.

The asyncio bridge thread has no Qt event loop: ``QTimer.singleShot`` or direct
widget calls from there never run (or crash). :func:`invoke_in_ui` goes through
a queued signal instead, which Qt delivers in the UI thread.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QCoreApplication, QObject, Qt, QThread, Signal, Slot

logger = logging.getLogger(__name__)


class _Invoker(QObject):
    call = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.call.connect(self._run, Qt.ConnectionType.QueuedConnection)

    @Slot(object)
    def _run(self, fn: Callable[[], Any]) -> None:
        try:
            fn()
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Error in a UI callback")


_invoker: _Invoker | None = None


def install_invoker() -> None:
    """Create the invoker. Must be called once from the UI thread, after QApplication."""
    global _invoker  # pylint: disable=global-statement
    app = QCoreApplication.instance()
    if app is None:
        raise RuntimeError("QApplication must exist before install_invoker()")
    if _invoker is None:
        _invoker = _Invoker()
        _invoker.moveToThread(app.thread())


def is_ui_thread() -> bool:
    """True if the caller runs in the Qt UI thread."""
    app = QCoreApplication.instance()
    return app is not None and QThread.currentThread() is app.thread()


def invoke_in_ui(fn: Callable[[], Any]) -> None:
    """Call ``fn()`` in the UI thread (always asynchronously, even from the UI thread)."""
    if _invoker is None:
        install_invoker()
    assert _invoker is not None
    _invoker.call.emit(fn)
