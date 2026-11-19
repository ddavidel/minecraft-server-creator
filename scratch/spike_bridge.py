"""
Spike T004 (research R-002): pymcsc in an asyncio loop on a background thread,
with its console output shown in a Qt widget through signals.

    python scratch/spike_bridge.py          # fake server (python subprocess)
    python scratch/spike_bridge.py --real [--version=1.21.4]   # real Vanilla server in a temp folder (needs Java,
                                            # downloads the server jar)
    add --auto to quit by itself once the server has started and stopped.

Not part of the package.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QPlainTextEdit  # noqa: E402

from mcsc import ServerManager, ServerState, ServerType, VanillaServer  # noqa: E402

from mcsc_gui.core.async_bridge import AsyncBridge  # noqa: E402


class FakeServer(VanillaServer):
    """Prints like a Minecraft server, but it's just Python."""

    def build_command(self) -> list[str]:
        script = (
            "import sys,time\n"
            "for i in range(200): print(f'[INFO] line {i}', flush=True)\n"
            "print('Done (0.1s)! For help, type \"help\"', flush=True)\n"
            "for line in sys.stdin:\n"
            "    if line.strip() == 'stop': print('Stopping server', flush=True); break\n"
        )
        return [sys.executable, "-u", "-c", script]

    @property
    def eula_accepted(self) -> bool:
        return True


class Events(QObject):
    line = Signal(str)
    state = Signal(str)
    done = Signal()


def main() -> None:
    real = "--real" in sys.argv
    auto = "--auto" in sys.argv
    app = QApplication(sys.argv)
    view = QPlainTextEdit(readOnly=True)
    view.resize(900, 500)
    view.show()

    events = Events()
    events.line.connect(view.appendPlainText)
    events.done.connect(app.quit)
    events.state.connect(lambda s: view.appendPlainText(f"=== state: {s} (UI thread: "
                                                        f"{threading.current_thread().name})"))

    bridge = AsyncBridge()
    bridge.start()
    tmp = tempfile.TemporaryDirectory()

    async def scenario() -> None:
        if real:
            manager = ServerManager(Path(tmp.name) / "servers")
            version = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--version=")), None)
            version = version or await asyncio.to_thread(manager.catalog.latest, ServerType.VANILLA)
            events.line.emit(f"Installing Vanilla {version}...")
            server = await manager.create_async("spike", version, ServerType.VANILLA,
                                                accept_eula=True, ram_gb=1)
        else:
            from mcsc import ServerConfig  # pylint: disable=import-outside-toplevel

            server = FakeServer(ServerConfig("spike", "1.0", path=Path(tmp.name)))

        def on_output(_server, line):
            events.line.emit(line)  # bridge thread -> queued to the UI thread

        def on_state(_server, _old, new):
            events.state.emit(f"{new} (listener thread: {threading.current_thread().name})")

        server.add_output_listener(on_output)
        server.add_state_listener(on_state)
        try:
            await server.start()
            while server.state is ServerState.STARTING:
                await asyncio.sleep(0.2)
            if server.is_active:
                await server.stop(60)
            events.state.emit(f"exit code {server.returncode}")
        finally:
            if auto:
                # Not QTimer.singleShot: this thread has no Qt event loop. Signals only.
                events.done.emit()

    future = bridge.submit(scenario())
    future.add_done_callback(lambda f: f.exception() and print("FAILED:", f.exception()))
    code = app.exec()
    bridge.shutdown()
    print("\n".join(view.toPlainText().splitlines()[-25:]))
    tmp.cleanup()
    sys.exit(code)


if __name__ == "__main__":
    main()
