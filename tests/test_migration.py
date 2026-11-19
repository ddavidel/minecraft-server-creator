import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcsc import ServerManager, ServerType

from mcsc_gui.core import migration
from mcsc_gui.core import server_manager as sm


class MigrateLegacyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.data_dir = root / "data"
        self.servers_dir = self.data_dir / "servers"
        self.data_dir.mkdir()

        # A legacy (v1) install: its own servers.json and server folders elsewhere
        legacy_root = root / "legacy"
        legacy_folder = legacy_root / "servers" / "old-1"
        legacy_folder.mkdir(parents=True)
        (legacy_folder / "server.jar").write_bytes(b"jar")
        (legacy_folder / "eula.txt").write_text("eula=true\n", encoding="utf-8")
        legacy_json = legacy_root / "servers.json"
        legacy_json.write_text(json.dumps({
            "old-1": {"name": "Legacy Paper", "version": "1.20.4", "jar_type": 1,
                      "dedicated_ram": 5, "address": "default", "port": 25570,
                      "uuid": "old-1", "folder_path": str(legacy_folder)},
        }), encoding="utf-8")
        (self.data_dir / migration.MIGRATION_FILENAME).write_text(str(legacy_json),
                                                                   encoding="utf-8")

        self.manager = ServerManager(self.servers_dir, self.data_dir / "config" / "servers.json")
        self.patch = mock.patch.object(sm, "manager", self.manager)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        sm._attached.clear()  # pylint: disable=protected-access
        self.tmp.cleanup()

    def migrate(self):
        return migration.migrate_legacy(self.data_dir, self.servers_dir)

    def test_servers_are_copied_and_registered(self):
        self.assertEqual(self.migrate(), 1)

        server = self.manager.get("old-1")
        self.assertEqual(server.config.name, "Legacy Paper")
        self.assertEqual(server.config.server_type, ServerType.PAPER)
        self.assertEqual(server.config.ram_gb, 5)
        self.assertEqual(server.path, self.servers_dir / "old-1")
        self.assertTrue((server.path / "server.jar").is_file())
        self.assertTrue(server.eula_accepted)

        self.assertFalse((self.data_dir / "migration.mgr").exists())
        self.assertTrue((self.data_dir / "migration.mgr.done").exists())

        # The registry is persisted with the new layout
        saved = ServerManager(self.servers_dir, self.data_dir / "config" / "servers.json")
        saved.load()
        self.assertEqual(saved.get("old-1").config.port, 25570)

    def test_no_migration_file_is_a_no_op(self):
        (self.data_dir / migration.MIGRATION_FILENAME).unlink()
        self.assertEqual(self.migrate(), 0)
        self.assertEqual(self.manager.servers, [])

    def test_already_migrated_servers_are_skipped(self):
        (self.servers_dir / "old-1").mkdir(parents=True)
        self.assertEqual(self.migrate(), 0)
        self.assertIsNone(self.manager.find("old-1"))
        self.assertTrue((self.data_dir / "migration.mgr.done").exists())


if __name__ == "__main__":
    unittest.main()
