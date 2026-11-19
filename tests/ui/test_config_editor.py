import yaml
from PySide6.QtCore import Qt

from mcsc_gui.ui import config_model as cm
from mcsc_gui.ui.pages.config_editor import ConfigEditorPage

PROPERTIES = (
    "#Minecraft server properties\n"
    "motd=A Minecraft Server\n"
    "max-players=20\n"
    "pvp=true\n"
    "level-seed=\n"
    "rate=007\n"
)


def value_item(model, key):
    root = model.invisibleRootItem()
    for row in range(root.rowCount()):
        if root.child(row, 0).text() == key:
            return root.child(row, 1)
    raise KeyError(key)


def test_properties_round_trip(qtbot, bridge, make_server):
    server = make_server()
    (server.server_dir / "server.properties").write_text(PROPERTIES, encoding="utf-8")

    page = ConfigEditorPage(server, "server.properties")
    qtbot.addWidget(page)
    qtbot.waitUntil(lambda: page.view is not None, timeout=2000)
    assert not page.dirty
    assert not page.save_button.isEnabled()

    value_item(page.model, "motd").setText("Hello from Qt")
    value_item(page.model, "max-players").setText("42")
    value_item(page.model, "pvp").setCheckState(Qt.CheckState.Unchecked)
    assert page.dirty
    assert not page.can_leave()
    assert page.save_button.isEnabled()

    with qtbot.waitSignal(page.saved, timeout=2000):
        page.save()
    assert not page.dirty

    text = (server.server_dir / "server.properties").read_text(encoding="utf-8")
    assert text.startswith("#Minecraft server properties\n")  # header kept
    assert server.read_config("server.properties") == {
        "motd": "Hello from Qt",
        "max-players": "42",
        "pvp": "false",
        "level-seed": "",
        "rate": "007",  # not an exact int: kept as text
    }


def test_nested_yaml_round_trip(make_server):
    server = make_server()
    data = {
        "settings": {"debug": False, "timeout": 30, "ratio": 0.5, "name": None},
        "worlds": ["world", "nether"],
        "top": "value",
    }
    (server.server_dir / "spigot.yml").write_text(yaml.safe_dump(data, sort_keys=False),
                                                  encoding="utf-8")
    loaded = server.read_config("spigot.yml")
    model = cm.build_model(loaded)
    assert not cm.is_flat(loaded)
    assert cm.model_to_data(model) == data

    settings = model.invisibleRootItem().child(0, 0)
    settings.child(1, 1).setText("45")  # timeout
    settings.child(0, 1).setCheckState(Qt.CheckState.Checked)  # debug
    settings.child(2, 1).setText("not a float")  # invalid: original kept
    server.write_config("spigot.yml", cm.model_to_data(model))

    reread = server.read_config("spigot.yml")
    assert reread["settings"] == {"debug": True, "timeout": 45, "ratio": 0.5, "name": None}
    assert reread["worlds"] == ["world", "nether"]


def test_unreadable_file_leaves_an_empty_usable_editor(qtbot, bridge, make_server):
    server = make_server()
    page = ConfigEditorPage(server, "server.properties")  # never generated
    qtbot.addWidget(page)
    qtbot.waitUntil(lambda: page.view is not None, timeout=2000)
    assert page.model.rowCount() == 0
    assert page.add_button.isEnabled()
    assert not page.dirty

    cm.add_entry(page.model, "motd", "")
    assert cm.model_to_data(page.model) == {"motd": ""}


def test_filter_matches_nested_keys(qtbot, bridge, make_server):
    server = make_server()
    (server.server_dir / "bukkit.yml").write_text(
        "settings:\n  allow-end: true\n  warn-on-overload: true\nspawn-limits:\n  monsters: 70\n",
        encoding="utf-8")
    page = ConfigEditorPage(server, "bukkit.yml")
    qtbot.addWidget(page)
    qtbot.waitUntil(lambda: page.view is not None, timeout=2000)
    page.search.setText("monsters")
    assert page.proxy.rowCount() == 1  # only "spawn-limits" (parent of the match)
