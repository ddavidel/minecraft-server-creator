"""Migration of servers created by MCSC v1 (legacy layout) to the current one."""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

from mcsc import ServerConfig

from mcsc_gui.config import settings as mcssettings
from mcsc_gui.core.server_manager import find_server, register_server

logger = logging.getLogger(__name__)

MIGRATION_FILENAME = "migration.mgr"


def migrate_legacy(
    data_dir: str | os.PathLike | None = None,
    servers_dir: str | os.PathLike | None = None,
) -> int:
    """
    Copy the servers listed by a legacy ``migration.mgr`` into ``servers_dir``.

    ``migration.mgr`` (written by the v1 uninstaller) holds the path of the legacy
    ``servers.json``. Servers already migrated are skipped. When done the file is
    renamed to ``migration.mgr.done``. Returns the number of migrated servers.
    """
    data_dir = Path(data_dir if data_dir is not None else mcssettings.DATA_DIR_PATH)
    servers_dir = Path(servers_dir if servers_dir is not None else mcssettings.SERVER_DIR_PATH)
    migration_file = data_dir / MIGRATION_FILENAME
    if not migration_file.exists():
        return 0

    logger.info("Detected servers migration for legacy version of MCSC")
    legacy_servers_json = migration_file.read_text(encoding="utf-8").strip()
    legacy_servers_dict = json.loads(Path(legacy_servers_json).read_text(encoding="utf-8"))

    migrated = 0
    for server_uuid, legacy_config in legacy_servers_dict.items():
        logger.info(f"Migrating server '{server_uuid}' ({legacy_config.get('name')})...")
        new_server_folder = servers_dir / server_uuid

        if new_server_folder.exists() or find_server(server_uuid) is not None:
            continue

        shutil.copytree(legacy_config["folder_path"], new_server_folder)

        # ServerConfig.from_dict understands the legacy keys (jar_type, dedicated_ram, ...)
        config = ServerConfig.from_dict({**legacy_config, "uuid": server_uuid})
        config.path = new_server_folder
        register_server(config)
        migrated += 1

    migration_file.rename(migration_file.with_suffix(".mgr.done"))
    logger.info("Migration completed successfully.")
    return migrated
