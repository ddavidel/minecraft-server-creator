"""
An asyncio event loop running in a dedicated background thread.

pymcsc is asyncio based (server processes are asyncio subprocesses), while the
Qt event loop owns the main thread. The UI never runs pymcsc code itself: it
hands coroutines to :meth:`AsyncBridge.submit` (or blocking functions to
:meth:`AsyncBridge.call`) and gets a :class:`concurrent.futures.Future` back.

pymcsc listeners therefore run in the bridge thread: they must never touch UI
widgets. No UI toolkit is imported here.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import logging
import sys
import threading
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AsyncBridge:
    """Runs an asyncio loop in a daemon thread and schedules work on it."""

    def __init__(self, name: str = "mcsc-asyncio") -> None:
        self._name = name
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._stopped = False

    # ------------------------------------------------------------- lifecycle

    def start(self) -> None:
        """Start the thread and the loop. Idempotent. Blocks until the loop is ready."""
        with self._lock:
            if self._stopped:
                raise RuntimeError("bridge stopped")
            if self._thread is not None:
                return
            self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
            self._thread.start()
        self._ready.wait()

    def _run(self) -> None:
        if sys.platform == "win32":
            # Subprocesses need the proactor loop on Windows (the default since 3.8,
            # made explicit because this loop doesn't live in the main thread).
            loop: asyncio.AbstractEventLoop = asyncio.ProactorEventLoop()
        else:
            loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        loop.call_soon(self._ready.set)
        try:
            loop.run_forever()
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.run_until_complete(loop.shutdown_default_executor())
            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception("Error while closing the asyncio loop")
            finally:
                loop.close()
                logger.debug("asyncio bridge loop closed")

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """The bridge's event loop (only valid after :meth:`start`)."""
        if self._loop is None:
            raise RuntimeError("bridge not started")
        return self._loop

    @property
    def is_running(self) -> bool:
        """True between :meth:`start` and :meth:`shutdown`."""
        return self._loop is not None and not self._stopped and self._loop.is_running()

    @property
    def thread(self) -> threading.Thread | None:
        """The bridge thread (``None`` before :meth:`start`)."""
        return self._thread

    def in_bridge_thread(self) -> bool:
        """True if the caller runs in the bridge thread."""
        return threading.current_thread() is self._thread

    # ------------------------------------------------------------------ work

    def submit(self, coro: Coroutine[Any, Any, T]) -> concurrent.futures.Future[T]:
        """Schedule ``coro`` on the loop. Thread-safe. Raises ``RuntimeError`` once stopped."""
        if self._stopped or self._loop is None:
            coro.close()  # avoid "coroutine was never awaited"
            raise RuntimeError("bridge stopped" if self._stopped else "bridge not started")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def call(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> concurrent.futures.Future[T]:
        """Run a blocking function (I/O, requests, pip) in the loop's executor."""

        async def _in_executor() -> T:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, functools.partial(fn, *args, **kwargs))

        return self.submit(_in_executor())

    # -------------------------------------------------------------- shutdown

    def shutdown(self, timeout: float = 5.0) -> None:
        """Cancel the pending tasks, stop the loop and join the thread. Idempotent."""
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
        loop, thread = self._loop, self._thread
        if loop is None or thread is None:
            return

        if loop.is_running() and not self.in_bridge_thread():
            try:
                asyncio.run_coroutine_threadsafe(_cancel_pending(), loop).result(timeout)
            except (concurrent.futures.TimeoutError, RuntimeError):
                logger.warning("Timed out cancelling the pending asyncio tasks")
            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception("Error cancelling the pending asyncio tasks")
        try:
            loop.call_soon_threadsafe(loop.stop)
        except RuntimeError:
            pass  # loop already closed
        if not self.in_bridge_thread():
            thread.join(timeout)
            if thread.is_alive():
                logger.warning("asyncio bridge thread did not stop within %ss", timeout)


async def _cancel_pending() -> None:
    current = asyncio.current_task()
    tasks = [t for t in asyncio.all_tasks() if t is not current and not t.done()]
    for task in tasks:
        task.cancel()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
            logger.error(f"Exception during shutdown: {result}")


_bridge: AsyncBridge | None = None


def get_bridge() -> AsyncBridge:
    """The application-wide bridge (created, not started, on first use)."""
    global _bridge  # pylint: disable=global-statement
    if _bridge is None:
        _bridge = AsyncBridge()
    return _bridge
