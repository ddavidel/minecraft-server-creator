from mcsc import ServerState

from mcsc_gui.ui.pages.dashboard import DashboardPage
from mcsc_gui.ui.server_events import ServerEvents


def make_dashboard(qtbot, servers):
    events = ServerEvents(track_registry=False)
    events.attach_all(servers)
    registry = {s.id: s for s in servers}
    page = DashboardPage(events, servers=lambda: list(registry.values()), find=registry.get)
    page.resize(1100, 700)
    qtbot.addWidget(page)
    page.show()
    return page, events, registry


def test_cards_follow_server_state(qtbot, make_server):
    server = make_server()
    page, events, _registry = make_dashboard(qtbot, [server])
    try:
        card = page.cards["srv"]
        assert card.badge.state is ServerState.STOPPED
        assert card.start_button.isEnabled() and not card.stop_button.isEnabled()

        with qtbot.waitSignal(events.state_changed, timeout=1000):
            server._set_state(ServerState.STARTING)  # pylint: disable=protected-access
        assert card.badge.state is ServerState.STARTING
        assert card.badge.pulsing
        assert not card.start_button.isEnabled() and card.stop_button.isEnabled()

        with qtbot.waitSignal(events.state_changed, timeout=1000):
            server._set_state(ServerState.RUNNING)  # pylint: disable=protected-access
        assert card.badge.state is ServerState.RUNNING
        assert not card.badge.pulsing
        assert card.stop_button.isEnabled()
    finally:
        events.close()


def test_empty_state_and_live_add_remove(qtbot, make_server):
    page, events, registry = make_dashboard(qtbot, [])
    try:
        assert page.cards == {}
        assert page.empty_state.isVisible()

        server = make_server("new", "Brand new")
        registry["new"] = server
        events.server_added.emit("new")
        assert "new" in page.cards
        assert page.cards["new"].name_label.text() == "Brand new"
        assert not page.empty_state.isVisible()

        server.config.name = "Renamed"
        events.server_updated.emit("new")
        assert page.cards["new"].name_label.text() == "Renamed"

        events.server_removed.emit("new")
        assert page.cards == {}
        assert page.empty_state.isVisible()
    finally:
        events.close()


def test_grid_columns_follow_width(qtbot, make_server):
    servers = [make_server(f"s{i}") for i in range(4)]
    page, events, _registry = make_dashboard(qtbot, servers)
    try:
        page.resize(1400, 700)
        qtbot.waitUntil(lambda: page.grid.columns >= 3, timeout=1000)
        page.resize(600, 700)
        qtbot.waitUntil(lambda: page.grid.columns == 1, timeout=1000)
    finally:
        events.close()


def test_card_click_opens_server(qtbot, make_server):
    from PySide6.QtCore import Qt  # pylint: disable=import-outside-toplevel

    page, events, _registry = make_dashboard(qtbot, [make_server()])
    try:
        with qtbot.waitSignal(page.open_server, timeout=1000) as blocker:
            qtbot.mouseClick(page.cards["srv"].details_label, Qt.MouseButton.LeftButton)
        assert blocker.args == ["srv"]
    finally:
        events.close()
