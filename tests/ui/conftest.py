import os

# Widget tests run headless (CI and terminals without a display).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from mcsc import PaperServer, ServerConfig, ServerType  # noqa: E402

from mcsc_gui.core.async_bridge import AsyncBridge  # noqa: E402
from mcsc_gui.ui import tasks  # noqa: E402
from mcsc_gui.ui.invoke import install_invoker  # noqa: E402


@pytest.fixture(autouse=True)
def _ui_setup(qapp):
    from mcsc_gui.ui.theme.qss import build_stylesheet  # pylint: disable=import-outside-toplevel

    install_invoker()
    qapp.setStyleSheet(build_stylesheet())
    yield


@pytest.fixture
def bridge():
    """A running bridge wired into ui.tasks (no toasts)."""
    b = AsyncBridge()
    b.start()
    tasks.configure(b, None)
    yield b
    b.shutdown()
    tasks.configure(None, None)


@pytest.fixture
def host(qtbot):
    from PySide6.QtWidgets import QWidget  # pylint: disable=import-outside-toplevel

    widget = QWidget()
    widget.resize(1100, 760)
    qtbot.addWidget(widget)
    widget.show()
    return widget


@pytest.fixture
def make_server(tmp_path: Path):
    def make(server_id="srv", name="Test", eula=True):
        path = tmp_path / server_id
        path.mkdir(parents=True, exist_ok=True)
        if eula:
            (path / "eula.txt").write_text("eula=true\n", encoding="utf-8")
        return PaperServer(ServerConfig(name, "1.21.4", ServerType.PAPER, ram_gb=2,
                                        id=server_id, path=path))
    return make
