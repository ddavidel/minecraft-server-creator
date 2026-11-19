"""
Take the README screenshots with demo servers.

The app runs on a throwaway data folder (your real servers and settings are
never read or touched), telemetry and the update check are disabled, and the
servers are fake: no Java process is started.

Usage: python scripts/take_screenshots.py [--lang en|it] [--out assets/screenshots]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import sys
import tempfile
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

parser = argparse.ArgumentParser()
parser.add_argument("--lang", default="en", choices=["en", "it"])
parser.add_argument("--out", default=str(ROOT / "assets" / "screenshots"))
ARGS = parser.parse_args()

# ----------------------------------------------------- isolated data folder
# Must happen before anything imports mcsc_gui (paths are computed at import).
DATA = Path(tempfile.mkdtemp(prefix="mcsc-screenshots-"))
import appdirs  # noqa: E402

appdirs.user_data_dir = lambda *_a, **_k: str(DATA)
(DATA / "config").mkdir(parents=True)
(DATA / "config" / "user_settings.json").write_text(
    json.dumps({"language": ARGS.lang, "shortcut_prompt_shown": True}), encoding="utf-8"
)
os.environ.pop("MCSC_DEBUG", None)

sys.path.insert(0, str(ROOT / "src"))

# pylint: disable=wrong-import-position
from mcsc_gui._pymcsc_check import ensure_pymcsc  # noqa: E402

ensure_pymcsc()

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from mcsc import ResourceUsage, ServerConfig, ServerState, ServerType  # noqa: E402

from mcsc_gui import telemetry  # noqa: E402
from mcsc_gui.config import settings as mcssettings  # noqa: E402
from mcsc_gui.core import server_manager as sm  # noqa: E402

assert Path(mcssettings.DATA_DIR_PATH) == DATA, "data folder not isolated"

# Nothing leaves the machine: no telemetry, no version lists, no update check
telemetry.TelemetryClient._send = lambda self, payload: True  # pylint: disable=protected-access
DEMO_VERSIONS = ["1.21.4", "1.21.3", "1.21.1", "1.20.6", "1.20.4", "1.20.1", "1.19.4"]
sm.get_versions = lambda _type: list(DEMO_VERSIONS)
sm.preload_versions = lambda: None

from mcsc_gui.core.async_bridge import get_bridge  # noqa: E402
from mcsc_gui.ui import tasks  # noqa: E402
from mcsc_gui.ui.invoke import install_invoker  # noqa: E402
from mcsc_gui.ui.main_window import MainWindow  # noqa: E402
from mcsc_gui.ui.server_events import ServerEvents  # noqa: E402
from mcsc_gui.ui.theme.fonts import load_fonts  # noqa: E402
from mcsc_gui.ui.theme.qss import build_stylesheet  # noqa: E402
from mcsc_gui.ui.usage import usage_history  # noqa: E402

# --------------------------------------------------------------- demo data

SERVER_PROPERTIES = """\
#Minecraft server properties
allow-flight=false
difficulty=normal
enable-command-block=false
enforce-whitelist=false
gamemode=survival
hardcore=false
level-name=world
level-seed=
max-players=20
motd=A Minecraft Server
online-mode=true
pvp=true
server-port={port}
simulation-distance=10
spawn-protection=16
view-distance=10
white-list=false
"""

LOG = """\
[18:02:11 INFO]: Starting minecraft server version {version}
[18:02:11 INFO]: Loading properties
[18:02:11 INFO]: This server is running Paper version {version} (Implementing API version {version}-R0.1-SNAPSHOT)
[18:02:12 INFO]: Using 4 threads for Netty based IO
[18:02:12 INFO]: Default game type: SURVIVAL
[18:02:12 INFO]: Generating keypair
[18:02:12 INFO]: Starting Minecraft server on *:{port}
[18:02:13 INFO]: Preparing level "world"
[18:02:15 INFO]: Preparing start region for dimension minecraft:overworld
[18:02:16 INFO]: Time elapsed: 2213 ms
[18:02:16 INFO]: Preparing start region for dimension minecraft:the_nether
[18:02:16 INFO]: Time elapsed: 412 ms
[18:02:16 INFO]: Preparing start region for dimension minecraft:the_end
[18:02:17 INFO]: Time elapsed: 301 ms
[18:02:17 INFO]: Running delayed init tasks
[18:02:17 INFO]: Done (6.184s)! For help, type "help"
[18:04:39 INFO]: Steve joined the game
[18:04:52 INFO]: Alex joined the game
[18:05:03 INFO]: <Steve> hi!
[18:05:07 INFO]: <Alex> let's build the castle near spawn
[18:07:21 WARN]: Can't keep up! Is the server overloaded? Running 2104ms or 42 ticks behind
[18:09:44 INFO]: Steve has made the advancement [Stone Age]
[18:12:30 INFO]: [Server] Backup completed
[18:13:02 INFO]: There are 2 of a max of 20 players online: Steve, Alex
[18:13:15 INFO]: Alex has made the advancement [Acquire Hardware]
"""

# name, version, type, RAM, port, state
DEMO_SERVERS = [
    ("Survival SMP", "1.21.4", ServerType.PAPER, 6, 25565, ServerState.RUNNING),
    ("Creative World", "1.21.1", ServerType.VANILLA, 4, 25566, ServerState.STOPPED),
    ("Modded Adventure", "1.20.1", ServerType.FORGE, 8, 25567, ServerState.STOPPED),
    ("Minigames", "1.21.4", ServerType.PAPER, 4, 25568, ServerState.RUNNING),
    ("Snapshot Test", "1.21.3", ServerType.VANILLA, 2, 25569, ServerState.STOPPED),
]


class FakeMonitor:
    """Plausible, slowly changing resource usage (no real process)."""

    def __init__(self, ram_gb: int, seed: int) -> None:
        self._rng = random.Random(seed)
        self._t = 0
        self._ram = ram_gb * 1024

    def _next(self) -> ResourceUsage:
        self._t += 1
        t, r = self._t, self._rng
        return ResourceUsage(
            ram_mb=self._ram * (0.55 + 0.08 * math.sin(t / 9)) + r.uniform(-40, 40),
            cpu_percent=max(1.0, 18 + 9 * math.sin(t / 5) + r.uniform(-4, 4)),
            disk_read_mb=max(0.0, 0.6 + 0.5 * math.sin(t / 4) + r.uniform(-0.2, 0.3)),
            disk_write_mb=max(0.0, 1.1 + 0.9 * math.sin(t / 6 + 1) + r.uniform(-0.3, 0.3)),
        )

    @property
    def usage(self) -> ResourceUsage:
        return self._next()

    def stop(self) -> None:
        pass


def create_demo_servers() -> list:
    servers = []
    for index, (name, version, kind, ram, port, state) in enumerate(DEMO_SERVERS):
        server_id = f"demo-{index}"
        path = DATA / "servers" / server_id
        path.mkdir(parents=True)
        (path / "eula.txt").write_text("eula=true\n", encoding="utf-8")
        if state is not ServerState.STOPPED or index % 2 == 0:
            (path / "server.properties").write_text(
                SERVER_PROPERTIES.format(port=port), encoding="utf-8")
        if kind is ServerType.PAPER:
            (path / "bukkit.yml").write_text("settings:\n  allow-end: true\n", encoding="utf-8")
            (path / "spigot.yml").write_text("settings:\n  debug: false\n", encoding="utf-8")
        server = sm.register_server(ServerConfig(name, version, kind, ram_gb=ram, port=port,
                                                 id=server_id, path=path))
        if state is not ServerState.STOPPED:
            server._state = state  # pylint: disable=protected-access
            server.monitor = FakeMonitor(ram, index)
            server.output.extend(LOG.format(version=version, port=port).splitlines())
            history = deque(maxlen=60)
            for _ in range(60):
                history.append(server.monitor.usage)
            usage_history._samples[server.id] = history  # pylint: disable=protected-access
        servers.append(server)
    return servers


# ------------------------------------------------------------------- shots

def main() -> int:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    install_invoker()
    app.setStyle("Fusion")
    load_fonts()
    app.setStyleSheet(build_stylesheet())

    servers = create_demo_servers()
    bridge = get_bridge()
    bridge.start()
    events = ServerEvents()
    events.attach_all(servers)
    window = MainWindow(events, bridge)
    tasks.configure(bridge, window.toasts)
    window.resize(1300, 800)
    window.show()

    out = Path(ARGS.out)
    out.mkdir(parents=True, exist_ok=True)
    suffix = "" if ARGS.lang == "en" else f"-{ARGS.lang}"
    running = servers[0]

    def shot(name: str) -> None:
        path = out / f"{name}{suffix}.png"
        window.grab().save(str(path))
        print(f"saved {path}")

    steps = [
        (1500, lambda: shot("dashboard")),
        (100, lambda: window.navigator.to_server(running.id)),
        (2500, lambda: shot("server")),
        (100, lambda: window.navigator.to_editor(running.id, "server.properties")),
        (1500, lambda: shot("editor")),
        (100, window.navigator.to_dashboard),
        (800, window.open_create_dialog),
        (1500, lambda: shot("new-server")),
        (100, app.quit),
    ]

    def run(index: int = 0) -> None:
        if index < len(steps):
            delay, action = steps[index]
            QTimer.singleShot(delay, lambda: (action(), run(index + 1)))

    run()
    app.exec()
    # The fake servers have no process: skip the normal shutdown (it would stop them)
    events.close()
    shutil.rmtree(DATA, ignore_errors=True)
    os._exit(0)  # pylint: disable=protected-access


if __name__ == "__main__":
    sys.exit(main())
