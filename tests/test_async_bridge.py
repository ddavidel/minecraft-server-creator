import asyncio
import sys
import threading
import time

import pytest

from mcsc_gui.core.async_bridge import AsyncBridge


@pytest.fixture
def bridge():
    b = AsyncBridge()
    b.start()
    yield b
    b.shutdown()


def test_submit_returns_result(bridge):
    assert bridge.submit(asyncio.sleep(0, result=42)).result(1) == 42


def test_start_is_idempotent(bridge):
    thread = bridge.thread
    bridge.start()
    assert bridge.thread is thread
    assert bridge.is_running


def test_coroutine_runs_in_bridge_thread(bridge):
    async def which_thread():
        return threading.current_thread()

    assert bridge.submit(which_thread()).result(1) is bridge.thread


def test_exception_goes_into_future(bridge):
    async def boom():
        raise ValueError("boom")

    future = bridge.submit(boom())
    assert isinstance(future.exception(1), ValueError)


def test_call_runs_blocking_function_off_the_loop(bridge):
    def blocking(a, b=0):
        time.sleep(0.05)
        return threading.current_thread(), a + b

    thread, value = bridge.call(blocking, 1, b=2).result(2)
    assert value == 3
    assert thread is not bridge.thread  # executor thread, the loop stays free


def test_subprocess_from_bridge_thread(bridge):
    # pymcsc runs Java through asyncio subprocesses: they must work from the
    # bridge thread (needs the proactor loop on Windows).
    async def run():
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", "print(1)", stdout=asyncio.subprocess.PIPE
        )
        out, _ = await proc.communicate()
        return proc.returncode, out.strip()

    assert bridge.submit(run()).result(15) == (0, b"1")


def test_shutdown_cancels_pending_and_joins():
    b = AsyncBridge()
    b.start()
    cancelled = threading.Event()

    async def forever():
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    future = b.submit(forever())
    time.sleep(0.05)
    started = time.monotonic()
    b.shutdown(timeout=5)
    assert time.monotonic() - started < 5
    assert cancelled.is_set()
    assert future.cancelled()
    assert not b.thread.is_alive()
    b.shutdown()  # idempotent


def test_submit_after_shutdown_raises():
    b = AsyncBridge()
    b.start()
    b.shutdown()
    with pytest.raises(RuntimeError, match="bridge stopped"):
        b.submit(asyncio.sleep(0))
    with pytest.raises(RuntimeError):
        b.start()
