"""OS shutdown or logoff while the app runs in the tray."""

from __future__ import annotations

from unittest import mock

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from mcsc_gui.ui import session_end as se


class FakeApp(QObject):
    aboutToQuit = Signal()  # noqa: N815 - Qt API


class FakeEvents(QObject):
    state_changed = Signal(str, str, str)
    busy_changed = Signal(str)


class FakeWindow(QWidget):
    ui_rebuilt = Signal()


class FakeBlocker:
    supported = True

    def __init__(self):
        self.hwnd = None
        self.reason = None

    def block(self, hwnd, reason):
        self.hwnd, self.reason = hwnd, reason

    def release(self):
        self.hwnd = self.reason = None


@pytest.fixture
def setup(qtbot):
    window = FakeWindow()
    qtbot.addWidget(window)
    window.quit_ready = False
    app, events, blocker = FakeApp(), FakeEvents(), FakeBlocker()
    busy = {"value": False}
    calls = []
    with mock.patch.object(se, "_busy", lambda: busy["value"]), \
            mock.patch.object(se.sm, "pending_backups", lambda: 0), \
            mock.patch.object(se, "emergency_stop", lambda b, t: calls.append(("stop", t))), \
            mock.patch.object(se.session, "end", lambda: calls.append(("end",))), \
            mock.patch.object(se.session, "send_app_close",
                              lambda reason: calls.append(("app_close", reason))):
        handler = se.SessionEndHandler(app, window, events, bridge=None, blocker=blocker)
        yield handler, app, events, blocker, busy, calls


def test_session_end_stops_servers_then_sends_app_close(setup):
    handler, app, _events, blocker, busy, calls = setup
    busy["value"] = True
    handler.refresh_block()
    app.aboutToQuit.emit()
    assert [c[0] for c in calls] == ["stop", "end", "app_close"]
    assert calls[-1] == ("app_close", "session_end")
    assert blocker.hwnd is None  # released once done
    app.aboutToQuit.emit()  # Qt may emit it more than once
    assert len(calls) == 3


def test_normal_quit_does_nothing_more(setup):
    handler, app, _events, _blocker, _busy, calls = setup
    handler.window.quit_ready = True
    app.aboutToQuit.emit()
    assert calls == []


def test_shutdown_is_blocked_only_while_busy(setup):
    _handler, _app, events, blocker, busy, _calls = setup
    busy["value"] = True
    events.state_changed.emit("srv", "stopped", "running")
    assert blocker.hwnd and blocker.reason
    busy["value"] = False
    events.busy_changed.emit("srv")
    assert blocker.hwnd is None


def test_block_is_renewed_when_the_window_is_rebuilt(setup):
    handler, _app, _events, blocker, busy, _calls = setup
    busy["value"] = True
    handler.refresh_block()
    blocker.reason = "old language"
    handler.window.ui_rebuilt.emit()
    assert blocker.reason != "old language"
