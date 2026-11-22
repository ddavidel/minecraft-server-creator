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


# ------------------------------------------------------------- context menu


def menu_actions(menu):
    return {a.text(): a for a in menu.actions() if not a.isSeparator()}


def test_card_menu_has_edit_clone_delete(qtbot, make_server):
    page, events, _registry = make_dashboard(qtbot, [make_server()])
    try:
        card = page.cards["srv"]
        menu = card.build_menu()
        assert [a.text() for a in menu.actions()] == [
            "Edit", "Clone", "Start when the app opens", "", "Delete"]
        actions = menu_actions(menu)
        assert menu.danger_item(actions["Delete"]) is not None  # drawn in red
        assert menu.danger_item(actions["Edit"]) is None
        for text, signal in (("Edit", page.edit_server), ("Clone", page.clone_server),
                             ("Delete", page.delete_server)):
            assert actions[text].isEnabled()
            with qtbot.waitSignal(signal, timeout=1000) as blocker:
                actions[text].trigger()
            assert blocker.args == ["srv"]
    finally:
        events.close()


def test_card_menu_disables_clone_and_delete_when_not_stopped_or_busy(qtbot, make_server):
    from mcsc_gui.core import server_manager as sm  # pylint: disable=import-outside-toplevel

    server = make_server()
    page, events, _registry = make_dashboard(qtbot, [server])
    try:
        card = page.cards["srv"]
        server._state = ServerState.RUNNING  # pylint: disable=protected-access
        actions = menu_actions(card.build_menu())
        assert actions["Edit"].isEnabled()
        assert not actions["Clone"].isEnabled() and not actions["Delete"].isEnabled()
        assert actions["Clone"].toolTip() == "Stop the server to clone it"
        assert actions["Delete"].toolTip() == "Stop the server to delete it"

        server._state = ServerState.STOPPED  # pylint: disable=protected-access
        sm._operations[server.id] = "clone"  # pylint: disable=protected-access
        try:
            actions = menu_actions(card.build_menu())
            assert not actions["Clone"].isEnabled() and not actions["Delete"].isEnabled()
            assert actions["Clone"].toolTip() == "Cloning…"
        finally:
            sm._operations.clear()  # pylint: disable=protected-access
    finally:
        events.close()


def test_card_menu_opens_with_mouse_and_keyboard(qtbot, make_server):
    from PySide6.QtCore import QPoint, Qt  # pylint: disable=import-outside-toplevel
    from PySide6.QtGui import QContextMenuEvent  # pylint: disable=import-outside-toplevel
    from PySide6.QtWidgets import QApplication  # pylint: disable=import-outside-toplevel

    page, events, _registry = make_dashboard(qtbot, [make_server()])
    try:
        card = page.cards["srv"]
        event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5),
                                  card.mapToGlobal(QPoint(5, 5)))
        QApplication.sendEvent(card, event)
        menu = card.menu
        assert menu is not None and menu.isVisible()
        menu.close()
        qtbot.waitUntil(lambda: card.menu is None, timeout=1000)

        card.setFocus()
        qtbot.keyClick(card, Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier)
        menu = card.menu
        assert menu is not None and menu.isVisible()
        # The keyboard context menu event that may follow doesn't open a second menu
        QApplication.sendEvent(card, QContextMenuEvent(QContextMenuEvent.Reason.Keyboard,
                                                       QPoint(0, 0), card.mapToGlobal(QPoint())))
        assert card.menu is menu
        with qtbot.waitSignal(page.edit_server, timeout=1000):
            qtbot.keyClick(menu, Qt.Key.Key_Down)
            qtbot.keyClick(menu, Qt.Key.Key_Return)
        qtbot.waitUntil(lambda: card.menu is None, timeout=1000)
    finally:
        events.close()


def test_card_menu_delete_works_with_mouse_and_keyboard(qtbot, make_server):
    from PySide6.QtCore import Qt  # pylint: disable=import-outside-toplevel

    page, events, _registry = make_dashboard(qtbot, [make_server()])
    try:
        card = page.cards["srv"]
        menu = card.show_menu()
        delete = menu_actions(menu)["Delete"]
        center = menu.actionGeometry(delete).center()
        qtbot.mouseMove(menu, center)
        qtbot.waitUntil(lambda: menu.danger_item(delete).active, timeout=1000)
        with qtbot.waitSignal(page.delete_server, timeout=1000):
            qtbot.mouseClick(menu, Qt.MouseButton.LeftButton, pos=center)

        menu = card.show_menu()
        with qtbot.waitSignal(page.delete_server, timeout=1000):
            for _ in range(4):
                qtbot.keyClick(menu, Qt.Key.Key_Down)
            qtbot.keyClick(menu, Qt.Key.Key_Return)
    finally:
        events.close()


def test_card_menu_toggles_auto_start(qtbot, make_server, tmp_path, monkeypatch):
    from mcsc_gui.core import server_manager as sm  # pylint: disable=import-outside-toplevel
    from mcsc_gui.core.server_prefs import ServerPrefs  # pylint: disable=import-outside-toplevel

    monkeypatch.setattr(sm, "prefs", ServerPrefs(tmp_path / "prefs.json"))
    server = make_server()
    page, events, _registry = make_dashboard(qtbot, [server])
    try:
        card = page.cards["srv"]
        assert not card.auto_start_icon.isVisibleTo(card)
        action = menu_actions(card.build_menu())["Start when the app opens"]
        assert action.isCheckable() and not action.isChecked()
        action.trigger()
        assert sm.server_auto_start(server)
        card.refresh()
        assert card.auto_start_icon.isVisibleTo(card)
        action = menu_actions(card.build_menu())["Start when the app opens"]
        assert action.isChecked()
        action.trigger()
        assert not sm.server_auto_start(server)
    finally:
        events.close()
