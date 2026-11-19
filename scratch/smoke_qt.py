"""
End-to-end smoke run of the Qt app with an isolated data folder and a fake
(Python) server process. Saves screenshots to the folder given as argv[1].

Never touches the real user data and never sends telemetry. Not part of the package.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "scratch" / "shots")
OUT.mkdir(parents=True, exist_ok=True)

TMP = tempfile.mkdtemp(prefix="mcsc-smoke-")
import appdirs  # noqa: E402

appdirs.user_data_dir = lambda *a, **k: TMP  # isolate every data path

from mcsc import ServerConfig, ServerType, VanillaServer  # noqa: E402

FAKE = (
    "import sys,time\n"
    "for i in range(40): print(f'[12:00:{i%60:02d}] [Server thread/INFO]: Preparing spawn area: {i}%', flush=True)\n"
    "print('[12:00:41] [Server thread/WARN]: Can\\'t keep up! Is the server overloaded?', flush=True)\n"
    "print('[12:00:42] [Server thread/ERROR]: Something odd (just a test)', flush=True)\n"
    "print('[12:00:43] [Server thread/INFO]: Done (1.234s)! For help, type \"help\"', flush=True)\n"
    "for line in sys.stdin:\n"
    "    cmd=line.strip()\n"
    "    if cmd=='stop': print('[12:01:00] [Server thread/INFO]: Stopping server', flush=True); break\n"
    "    print(f'[12:00:50] [Server thread/INFO]: There are 0 of a max of 20 players online: ({cmd})', flush=True)\n"
)
from mcsc import ForgeServer, PaperServer  # noqa: E402

for _cls in (VanillaServer, PaperServer, ForgeServer):
    _cls.build_command = lambda self: [sys.executable, "-u", "-c", FAKE]

import mcsc_gui.telemetry as telemetry  # noqa: E402

telemetry.TelemetryClient._send = lambda self, payload: True  # no network
import mcsc_gui.ui.dialogs.update_app as update_app  # noqa: E402

update_app.check_for_updates = lambda: True  # pretend an update exists

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from mcsc_gui import qt_main  # noqa: E402
from mcsc_gui.core import server_manager as sm  # noqa: E402

# Two servers: one installed (eula + server.properties), one fresh
for name, sid, kind, ram in (("Survival", "s1", ServerType.PAPER, 4),
                             ("Creative world", "s2", ServerType.VANILLA, 2)):
    path = Path(TMP) / "servers" / sid
    path.mkdir(parents=True)
    (path / "eula.txt").write_text("eula=true\n", encoding="utf-8")
    sm.manager.register(ServerConfig(name, "1.21.4", kind, ram_gb=ram, id=sid, path=path))
(Path(TMP) / "servers" / "s1" / "server.properties").write_text(
    "#Minecraft server properties\nmotd=A Minecraft Server\nmax-players=20\npvp=true\n"
    "online-mode=true\nlevel-seed=\n", encoding="utf-8")
sm.manager.save()

steps = []


def step(delay_ms):
    def deco(fn):
        steps.append((delay_ms, fn))
        return fn
    return deco


def shot(name):
    window = QApplication.instance().property("mcsc_window")
    window.grab().save(str(OUT / f"{name}.png"))
    print("shot", name)


def window():
    return QApplication.instance().property("mcsc_window")


@step(1200)
def dashboard():
    shot("01_dashboard")
    card = window().dashboard.cards["s1"]
    card.start_button.click()


@step(1500)
def started():
    shot("02_dashboard_running")
    window().navigator.to_server("s1")


@step(2500)
def detail():
    page = window().navigator.current_page
    page.console.input.setText("list")
    page.console.input.returnPressed.emit()
    QTimer.singleShot(600, lambda: shot("03_detail"))


@step(1500)
def editor():
    window().navigator.to_editor("s1", "server.properties")


@step(1500)
def editor_shot():
    shot("04_editor")
    window().open_create_dialog()


@step(1500)
def create_dialog():
    shot("05_create_dialog")
    from mcsc_gui.ui.widgets.overlay_dialog import OverlayDialog
    for d in window().centralWidget().findChildren(OverlayDialog):
        d.reject()
    window().navigator.back()


@step(800)
def edit_dialog():
    page = window().navigator.current_page
    page.edit_requested.emit("s1")


@step(800)
def edit_shot():
    shot("06_edit_dialog")
    from mcsc_gui.ui.widgets.overlay_dialog import OverlayDialog
    for d in window().centralWidget().findChildren(OverlayDialog):
        d.reject()
    window().close()  # servers running -> confirmation


@step(800)
def quit_confirm():
    shot("07_quit_confirm")
    from mcsc_gui.ui.dialogs.confirm_quit import ConfirmQuitDialog
    for d in window().centralWidget().findChildren(ConfirmQuitDialog):
        d.accept()


def run_steps():
    total = 0
    for delay, fn in steps:
        total += delay
        QTimer.singleShot(total, fn)


original_init = qt_main.MainWindow.__init__


def patched_init(self, *a, **k):
    original_init(self, *a, **k)
    QApplication.instance().setProperty("mcsc_window", self)
    run_steps()


qt_main.MainWindow.__init__ = patched_init
code = qt_main.main(["smoke"])
print("exit code", code, "active servers:", [s.id for s in sm.manager.active_servers])
