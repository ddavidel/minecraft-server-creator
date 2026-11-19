"""
Safety net against orphan Java processes (FR-006, SC-005).

The normal exit path stops the servers from the UI (confirm -> ``stop_all`` ->
telemetry -> bridge shutdown). These helpers cover abnormal exits: interpreter
exit (``atexit``) and anything that skips the UI path. They block, so they must
not run in the bridge thread.
"""

from __future__ import annotations

import logging

import psutil

from mcsc_gui.config import settings as mcssettings
from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.async_bridge import AsyncBridge

logger = logging.getLogger(__name__)


def kill_server_processes() -> int:
    """Kill the process tree of every active server. Returns how many were killed."""
    killed = 0
    for server in sm.manager.active_servers:
        pid = server.pid
        if pid is None:
            continue
        try:
            root = psutil.Process(pid)
            processes = [*root.children(recursive=True), root]
        except psutil.NoSuchProcess:
            continue
        for process in processes:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
        psutil.wait_procs(processes, timeout=5)
        logger.warning(f"Killed server {server.id} (pid {pid})")
        killed += 1
    return killed


def emergency_stop(bridge: AsyncBridge | None, timeout: float | None = None) -> None:
    """Synchronously stop every active server; kill them if that's not possible."""
    if not sm.any_server_active():
        return
    timeout = timeout if timeout is not None else mcssettings.SERVER_STOP_TIMEOUT + 5
    logger.warning("Emergency stop of the running servers")
    if bridge is not None and bridge.is_running and not bridge.in_bridge_thread():
        try:
            bridge.submit(sm.stop_all_servers()).result(timeout)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(f"Graceful emergency stop failed: {e!r}")
    if sm.any_server_active():
        kill_server_processes()
