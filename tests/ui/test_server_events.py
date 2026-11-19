import threading
from pathlib import Path

import pytest

from mcsc import PaperServer, ServerConfig, ServerState, ServerType

from mcsc_gui.ui.server_events import ServerEvents


@pytest.fixture
def server(tmp_path: Path):
    return PaperServer(ServerConfig("Test", "1.21.4", ServerType.PAPER, id="srv", path=tmp_path))


@pytest.fixture
def events(qtbot):
    ev = ServerEvents(track_registry=False)
    yield ev
    ev.close()


def test_state_change_becomes_a_signal(qtbot, events, server):
    events.attach(server)
    with qtbot.waitSignal(events.state_changed, timeout=1000) as blocker:
        server._set_state(ServerState.STARTING)  # pylint: disable=protected-access
    assert blocker.args == ["srv", "stopped", "starting"]


def test_state_change_from_background_thread_arrives_in_ui_thread(qtbot, events, server):
    events.attach(server)
    received = []
    events.state_changed.connect(lambda *args: received.append(threading.current_thread()))
    thread = threading.Thread(
        target=server._set_state, args=(ServerState.RUNNING,)  # pylint: disable=protected-access
    )
    thread.start()
    thread.join()
    qtbot.waitUntil(lambda: bool(received), timeout=1000)
    assert received == [threading.main_thread()]


def test_attach_is_idempotent(events, server):
    events.attach(server)
    events.attach(server)
    assert len(server._output_listeners) == 1  # pylint: disable=protected-access
    assert len(server._state_listeners) == 1  # pylint: disable=protected-access


def test_10k_lines_batched_without_losses(qtbot, events, server):
    events.attach(server)
    received: list[str] = []
    emissions = []

    def on_lines(server_id, lines):
        assert server_id == "srv"
        emissions.append(len(lines))
        received.extend(lines)

    events.output_lines.connect(on_lines)
    total = 10_000

    def produce():
        for i in range(total):
            server._notify(server._output_listeners, f"line {i}")  # pylint: disable=protected-access

    thread = threading.Thread(target=produce)
    thread.start()
    thread.join()
    qtbot.waitUntil(lambda: len(received) == total, timeout=3000)

    assert received == [f"line {i}" for i in range(total)]
    assert len(emissions) <= 50  # batched, not one signal per line


def test_detach_removes_listeners(qtbot, events, server):
    events.attach(server)
    events.detach(server)
    assert server._output_listeners == []  # pylint: disable=protected-access
    assert server._state_listeners == []  # pylint: disable=protected-access
    assert not events.is_attached("srv")
    events.detach(server)  # no-op


def test_registry_callbacks_attach_and_emit(qtbot, tmp_path):
    from mcsc_gui.core import server_manager as sm  # pylint: disable=import-outside-toplevel

    ev = ServerEvents()
    try:
        srv = PaperServer(ServerConfig("X", "1.21.4", ServerType.PAPER, id="new", path=tmp_path))
        with qtbot.waitSignal(ev.server_added, timeout=1000) as blocker:
            sm._fire(sm._added_callbacks, srv)  # pylint: disable=protected-access
        assert blocker.args == ["new"]
        assert ev.is_attached("new")

        with qtbot.waitSignal(ev.server_removed, timeout=1000):
            sm._fire(sm._removed_callbacks, srv)  # pylint: disable=protected-access
        assert not ev.is_attached("new")
        assert srv._output_listeners == []  # pylint: disable=protected-access
    finally:
        ev.close()
    assert ev._on_server_added not in sm._added_callbacks  # pylint: disable=protected-access
