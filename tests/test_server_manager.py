import asyncio
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcsc import (
    EulaNotAcceptedError,
    ForgeServer,
    PaperServer,
    ServerConfig,
    ServerManager,
    ServerState,
    ServerType,
    VanillaServer,
    VersionCatalog,
)

from mcsc_gui.core import server_manager as sm
from mcsc_gui.core.notifier import NullNotifier, get_notifier, set_notifier


class CoreIsolationTests(unittest.TestCase):
    def test_core_imports_no_ui_toolkit(self):
        # Fresh interpreter: the test session itself may already have imported Qt.
        code = (
            "import sys\n"
            "import mcsc_gui.core.server_manager, mcsc_gui.core.migration\n"
            "import mcsc_gui.core.notifier, mcsc_gui.core.async_bridge\n"
            "import mcsc_gui.core.user_settings, mcsc_gui.core.logger\n"
            "bad = sorted({m.split('.')[0] for m in sys.modules} & {'nicegui', 'PySide6', 'webview'})\n"
            "print(','.join(bad))\n"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                                check=True)
        self.assertEqual(result.stdout.strip(), "")


class LegacyRegistryTests(unittest.TestCase):
    """servers.json written by MCSC < 3 must load with the same layout the app uses."""

    def test_load_legacy_servers_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            servers_dir = Path(tmp) / "servers"
            registry = Path(tmp) / "config" / "servers.json"
            registry.parent.mkdir()
            legacy = {
                "a": {"name": "Vanilla", "version": "1.21.4", "jar_type": 0, "dedicated_ram": 3,
                      "address": "default", "port": 25565, "uuid": "a",
                      "folder_path": str(servers_dir / "a") + "\\"},
                "b": {"name": "Paper", "version": "1.21.4", "jar_type": 1, "dedicated_ram": 4,
                      "address": "default", "port": 25566, "uuid": "b",
                      "folder_path": str(servers_dir / "b")},
                "c": {"name": "Forge", "version": "1.20.1-47.3.0", "jar_type": 2, "dedicated_ram": 6,
                      "address": "default", "port": 25567, "uuid": "c",
                      "folder_path": str(servers_dir / "c")},
            }
            registry.write_text(json.dumps(legacy), encoding="utf-8")

            manager = ServerManager(servers_dir, registry)
            manager.load()

            self.assertIsInstance(manager.get("a"), VanillaServer)
            self.assertIsInstance(manager.get("b"), PaperServer)
            self.assertIsInstance(manager.get("c"), ForgeServer)
            self.assertEqual(manager.get("a").config.ram_gb, 3)
            self.assertIsNone(manager.get("a").config.address)
            self.assertEqual(manager.get("a").path, servers_dir / "a")
            # Legacy Forge servers were installed in <folder>/server
            self.assertEqual(manager.get("c").server_dir, servers_dir / "c" / "server")


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        config = ServerConfig("Test", "1.21.4", ServerType.PAPER, ram_gb=4, id="abc",
                              path=Path(self.tmp.name))
        self.server = PaperServer(config)

    def tearDown(self):
        self.tmp.cleanup()

    def test_status_label_covers_every_state(self):
        for state in ServerState:
            self.assertTrue(sm.status_label(state))

    def test_error_message_translates_library_errors(self):
        self.assertEqual(sm.error_message(EulaNotAcceptedError("x")), "EULA not accepted")
        self.assertEqual(sm.error_message(ValueError("plain")), "plain")

    def test_telemetry_details_has_legacy_keys_and_no_paths(self):
        details = sm.telemetry_details(self.server)
        self.assertEqual(details["uuid"], "abc")
        self.assertEqual(details["jar_type"], 1)
        self.assertEqual(details["dedicated_ram"], 4)
        self.assertNotIn("path", details)
        self.assertNotIn("folder_path", details)

    def test_buttons_follow_state(self):
        self.assertTrue(sm.can_start(self.server))
        self.assertFalse(sm.can_stop(self.server))
        self.server._state = ServerState.RUNNING  # pylint: disable=protected-access
        self.assertFalse(sm.can_start(self.server))
        self.assertTrue(sm.can_stop(self.server))

    def test_config_file_exists_rejects_paths_outside_server(self):
        self.assertFalse(sm.config_file_exists(self.server, "../outside.yml"))
        (Path(self.tmp.name) / "spigot.yml").write_text("a: 1\n", encoding="utf-8")
        self.assertTrue(sm.config_file_exists(self.server, "spigot.yml"))

    def test_get_versions_filters_unstable(self):
        catalog = VersionCatalog(data={ServerType.VANILLA: {
            "1.21.4": "u1", "1.20.1": "u2", "25w01a": "u3"}})
        with mock.patch.object(sm.manager, "catalog", catalog):
            self.assertEqual(sm.get_versions(0), ["1.21.4", "1.20.1"])


class NotifierTests(unittest.TestCase):
    def tearDown(self):
        set_notifier(None)

    def test_notify_error_goes_through_registered_notifier(self):
        received = []

        class Recorder:
            def info(self, message):
                received.append(("info", message))

            def success(self, message):
                received.append(("success", message))

            def error(self, message):
                received.append(("error", message))

        set_notifier(Recorder())
        sm.notify_error(EulaNotAcceptedError("x"))
        self.assertEqual(received, [("error", "EULA not accepted")])

    def test_default_notifier_is_null(self):
        set_notifier(None)
        self.assertIsInstance(get_notifier(), NullNotifier)
        get_notifier().error("logged only")


class RegistryCallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.manager = ServerManager(Path(self.tmp.name) / "servers",
                                     Path(self.tmp.name) / "servers.json")
        self.patch = mock.patch.object(sm, "manager", self.manager)
        self.patch.start()
        self.events = []
        self.callbacks = [
            lambda s: self.events.append(("added", s.id)),
            lambda s: self.events.append(("removed", s.id)),
            lambda s: self.events.append(("updated", s.id)),
        ]
        sm.on_server_added(self.callbacks[0])
        sm.on_server_removed(self.callbacks[1])
        sm.on_server_updated(self.callbacks[2])

    def tearDown(self):
        for callback in self.callbacks:
            sm.remove_callback(callback)
        self.patch.stop()
        sm._attached.clear()  # pylint: disable=protected-access
        self.tmp.cleanup()

    def test_register_update_delete_fire_callbacks(self):
        config = ServerConfig("A", "1.21.4", ServerType.VANILLA, id="x",
                              path=Path(self.tmp.name) / "servers" / "x")
        server = sm.register_server(config)
        sm.update_server(server, " Renamed ", 3)

        async def fake_send(event, details=None):
            pass

        with mock.patch.object(sm, "send_event_async", fake_send):
            asyncio.run(sm.delete_server(server, delete_files=False))

        self.assertEqual(self.events, [("added", "x"), ("updated", "x"), ("removed", "x")])
        self.assertEqual(server.config.name, "Renamed")
        self.assertEqual(server._state_listeners, [])  # pylint: disable=protected-access

    def test_failing_callback_doesnt_break_the_operation(self):
        def boom(_server):
            raise RuntimeError("boom")

        sm.on_server_added(boom)
        try:
            config = ServerConfig("A", "1.21.4", id="y", path=Path(self.tmp.name) / "y")
            sm.register_server(config)
        finally:
            sm.remove_callback(boom)
        self.assertIn(("added", "y"), self.events)


class CreateServerTests(unittest.TestCase):
    def test_create_validates_and_sends_telemetry(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ServerManager(Path(tmp) / "servers")
            fake_server = PaperServer(ServerConfig("New", "1.21.4", ServerType.PAPER,
                                                   path=Path(tmp) / "x"))
            sent = []

            async def fake_send(event, details=None):
                sent.append(event)

            async def fake_create(*args, **kwargs):
                return fake_server

            with mock.patch.object(sm, "manager", manager), \
                    mock.patch.object(manager, "create_async", side_effect=fake_create) as create, \
                    mock.patch.object(sm, "send_event_async", fake_send):
                with self.assertRaises(ValueError):
                    asyncio.run(sm.create_server("  ", "1.21.4", 1, 2, True))

                server = asyncio.run(sm.create_server(" New ", "1.21.4", 1, 2, True))

            self.assertIs(server, fake_server)
            create.assert_called_once_with("New", "1.21.4", ServerType.PAPER,
                                           accept_eula=True, ram_gb=2)
            self.assertEqual(sent, ["server_create"])


if __name__ == "__main__":
    unittest.main()
