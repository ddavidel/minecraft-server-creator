import pytest
from PySide6.QtWidgets import QWidget
from shiboken6 import isValid

from mcsc_gui.ui.widgets.toast import MAX_VISIBLE, ToastManager


@pytest.fixture
def host(qtbot):
    widget = QWidget()
    widget.resize(900, 600)
    qtbot.addWidget(widget)
    widget.show()
    return widget


@pytest.fixture
def toasts(host):
    return ToastManager(host)


def test_at_most_four_visible(qtbot, toasts):
    handles = [toasts.info(f"message {i}", timeout_ms=10_000) for i in range(6)]
    assert len(toasts.visible_toasts) == MAX_VISIBLE
    # The oldest ones were closed, the newest kept
    assert not handles[0].is_open and not handles[1].is_open
    assert [t.message for t in toasts.visible_toasts] == [f"message {i}" for i in range(2, 6)]
    qtbot.waitUntil(lambda: not isValid(handles[0].toast), timeout=2000)


def test_toasts_stack_bottom_right_newest_last(qtbot, toasts, host):
    first = toasts.info("first", timeout_ms=10_000).toast
    second = toasts.info("second", timeout_ms=10_000).toast
    qtbot.wait(300)  # let the slide-in finish
    assert second.y() > first.y()
    assert second.geometry().bottom() <= host.height()
    assert second.geometry().right() <= host.width()


def test_auto_dismiss(qtbot, toasts):
    handle = toasts.success("bye", timeout_ms=50)
    qtbot.waitUntil(lambda: not handle.is_open, timeout=1000)
    qtbot.waitUntil(lambda: not isValid(handle.toast), timeout=2000)
    assert toasts.visible_toasts == []


def test_progress_stays_until_resolved(qtbot, toasts):
    handle = toasts.progress("working")
    toast = handle.toast
    assert toast.level == "progress"
    assert not toast.timer_active
    qtbot.wait(100)
    assert handle.is_open

    handle.update("still working")
    assert toast.message == "still working"

    handle.succeed("done", timeout_ms=50)
    assert toast.level == "success"
    assert toast.message == "done"
    qtbot.waitUntil(lambda: not handle.is_open, timeout=1000)


def test_progress_fail_and_closed_handle(qtbot, toasts):
    handle = toasts.progress("working")
    handle.fail("broken", timeout_ms=10_000)
    assert handle.toast.level == "error"
    handle.dismiss()
    assert not handle.is_open
    # Resolving a closed handle shows a new toast instead of failing
    handle.succeed("late result")
    assert [t.message for t in toasts.visible_toasts] == ["late result"]
