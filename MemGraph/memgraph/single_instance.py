"""Single-instance guard.

Ensures only one MemGraph widget runs at a time. A second launch (e.g. the user
double-clicking the exe again) detects the running instance, asks it to surface
itself, and then exits instead of opening a duplicate.

Implementation: a ``QSharedMemory`` segment claims a unique key; if the claim
fails, another instance already holds it. A ``QLocalServer``/``QLocalSocket``
pair lets the new process ping the existing one to show/raise its window.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6 import QtCore, QtNetwork


_KEY = "MemGraph_single_instance_v1"
_PIPE = "MemGraph_ipc_v1"
_PING = b"show"


class SingleInstance(QtCore.QObject):
    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._shared = QtCore.QSharedMemory(_KEY)
        self._server: Optional[QtNetwork.QLocalServer] = None
        self._on_activate: Optional[Callable[[], None]] = None
        # create() succeeds only if no other process holds the segment.
        self._primary = self._shared.create(1)

    @property
    def is_primary(self) -> bool:
        return self._primary

    def start_server(self, on_activate: Callable[[], None]) -> None:
        """Primary instance: listen for pings from future launches."""
        if not self._primary:
            return
        self._on_activate = on_activate
        QtNetwork.QLocalServer.removeServer(_PIPE)
        self._server = QtNetwork.QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        self._server.listen(_PIPE)

    def _on_new_connection(self) -> None:
        if not self._server:
            return
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        # We don't even need to read the payload — any connection means
        # "another launch happened, please surface yourself".
        if self._on_activate:
            self._on_activate()
        conn.disconnectFromServer()

    def ping_primary(self, timeout_ms: int = 500) -> bool:
        """Secondary instance: tell the primary to show itself. Returns True
        if the primary was reached."""
        sock = QtNetwork.QLocalSocket()
        sock.connectToServer(_PIPE)
        if not sock.waitForConnected(timeout_ms):
            return False
        sock.write(_PING)
        sock.flush()
        sock.waitForBytesWritten(timeout_ms)
        sock.disconnectFromServer()
        return True
