"""Single app instance through a local socket (R-008)."""

from __future__ import annotations

import getpass
import hashlib
import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_MS = 500
ACTIVATE = b"activate"


def server_name(app_id: str = "mcsc") -> str:
    """Per-user socket name (two users on the same machine get one instance each)."""
    try:
        user = getpass.getuser()
    except Exception:  # pylint: disable=broad-exception-caught
        user = "user"
    digest = hashlib.sha1(f"{app_id}:{user}".encode()).hexdigest()[:12]
    return f"{app_id}-single-instance-{digest}"


class SingleInstance(QObject):
    """``acquire()`` returns False if another instance runs (and asks it to show itself)."""

    activated = Signal()

    def __init__(self, name: str | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.name = name or server_name()
        self._server: QLocalServer | None = None

    def acquire(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.name)
        if socket.waitForConnected(CONNECT_TIMEOUT_MS):
            socket.write(ACTIVATE)
            socket.flush()
            socket.waitForBytesWritten(CONNECT_TIMEOUT_MS)
            socket.disconnectFromServer()
            logger.info("Another instance is running: asked it to come to the front")
            return False

        # No live instance: a stale socket (crash) may be left behind
        QLocalServer.removeServer(self.name)
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not self._server.listen(self.name):
            logger.warning(f"Single instance server failed: {self._server.errorString()}")
            return True  # don't prevent the app from running
        self._server.newConnection.connect(self._on_connection)
        return True

    def _on_connection(self) -> None:
        assert self._server is not None
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(socket.deleteLater)
            if socket.bytesAvailable():
                self._read(socket)

    def _read(self, socket: QLocalSocket) -> None:
        if bytes(socket.readAll()).startswith(ACTIVATE):
            self.activated.emit()

    def release(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
