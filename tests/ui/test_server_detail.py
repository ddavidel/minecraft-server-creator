import gc

from PySide6.QtCore import SIGNAL
from PySide6.QtWidgets import QStackedWidget, QWidget

from mcsc import ResourceUsage, ServerState

from mcsc_gui.ui.navigator import Navigator, Route
from mcsc_gui.ui.pages.server_detail import ServerDetailPage
from mcsc_gui.ui.server_events import ServerEvents
from mcsc_gui.ui.usage import UsageHistory


def receivers(events: ServerEvents) -> int:
    return (events.receivers(SIGNAL("output_lines(QString,QVariantList)"))
            + events.receivers(SIGNAL("state_changed(QString,QString,QString)")))


def test_open_close_detail_50_times_leaves_no_listeners(qtbot, make_server):
    """SC-004: entering/leaving the detail page doesn't leak listeners or pages."""
    server = make_server()
    server.output.extend(f"old {i}" for i in range(10))
    events = ServerEvents(track_registry=False)
    events.attach(server)
    stack = QStackedWidget()
    qtbot.addWidget(stack)
    dashboard = QWidget()
    navigator = Navigator(stack, dashboard,
                          lambda route: ServerDetailPage(server, events), animate=False)
    try:
        baseline = receivers(events)
        for _ in range(50):
            navigator.to_server(server.id)
            page = navigator.current_page
            assert isinstance(page, ServerDetailPage)
            assert page.console.line_count() == 10  # buffered output, no duplicates
            navigator.back()
        qtbot.wait(10)
        gc.collect()

        assert receivers(events) == baseline
        assert stack.count() == 1  # only the dashboard is left
        assert len(server._output_listeners) == 1  # pylint: disable=protected-access
        assert len(server._state_listeners) == 1  # pylint: disable=protected-access
        assert navigator.history == [Route("dashboard")]
    finally:
        events.close()


def test_detail_streams_output_and_state(qtbot, make_server):
    server = make_server()
    events = ServerEvents(track_registry=False)
    events.attach(server)
    page = ServerDetailPage(server, events, history=UsageHistory())
    qtbot.addWidget(page)
    try:
        assert not page.console.input.isEnabled()  # stopped: no commands
        with qtbot.waitSignal(events.state_changed, timeout=1000):
            server._set_state(ServerState.STARTING)  # pylint: disable=protected-access
        assert page.console.input.isEnabled()
        assert page.stop_button.isEnabled() and not page.start_button.isEnabled()

        server._notify(server._output_listeners, "hello")  # pylint: disable=protected-access
        qtbot.waitUntil(lambda: page.console.log.toPlainText() == "hello", timeout=1000)

        server.monitor.usage = ResourceUsage(ram_mb=512, cpu_percent=12.5)
        page._sample_usage()  # pylint: disable=protected-access
        assert page.ram_tile.value_label.text() == "512 MB"
        assert page.cpu_tile.value_label.text() == "12.5 %"
    finally:
        page.dispose()
        events.close()


def test_config_files_visibility(qtbot, make_server):
    server = make_server()
    events = ServerEvents(track_registry=False)
    page = ServerDetailPage(server, events, history=UsageHistory())
    qtbot.addWidget(page)
    try:
        # server.properties is shown but disabled before the first start
        assert list(page.file_buttons) == ["server.properties"]
        assert not page.file_buttons["server.properties"].isEnabled()

        (server.server_dir / "server.properties").write_text("motd=x\n", encoding="utf-8")
        (server.server_dir / "spigot.yml").write_text("a: 1\n", encoding="utf-8")
        page.refresh()
        assert page.file_buttons["server.properties"].isEnabled()
        assert "spigot.yml" in page.file_buttons
        assert "bukkit.yml" not in page.file_buttons
    finally:
        page.dispose()
        events.close()
