"""Server console: the live log at full size and the command input."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from mcsc import MinecraftServer, ServerState

from mcsc_gui.config import settings as mcssettings
from mcsc_gui.core import server_manager as sm
from mcsc_gui.ui.navigator import CONSOLE
from mcsc_gui.ui.pages.server_base import ServerPage
from mcsc_gui.ui.server_events import ServerEvents
from mcsc_gui.ui.tasks import run_task
from mcsc_gui.ui.widgets.console import ConsoleView


class ServerConsolePage(ServerPage):
    section = CONSOLE

    def __init__(self, server: MinecraftServer, events: ServerEvents,
                 parent: QWidget | None = None) -> None:
        super().__init__(server, events, parent)
        self.console = ConsoleView(mcssettings.MAX_LOG_LINES)
        self.console.command_submitted.connect(self._send_command)
        self.body.addWidget(self.console, 1)
        self.console.set_lines(list(server.output))
        self.refresh()

    def refresh(self) -> None:
        super().refresh()
        self.console.set_input_enabled(self.server.is_active)

    def on_state_changed(self, old: str, new: str) -> None:
        if new == ServerState.STARTING:
            self.console.set_lines([])  # pymcsc clears its buffer on start

    def on_output(self, lines: list) -> None:
        self.console.append_lines(lines)

    def _send_command(self, command: str) -> None:
        # "stop" is routed to stop_server (graceful, with SERVER_STOP_TIMEOUT)
        run_task(sm.send_command(self.server, command))
