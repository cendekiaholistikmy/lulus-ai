"""Enforce and measure "no data leaves the machine".

`NetworkGuard` blocks every outbound socket connection while a check
runs and counts the attempts, so the benchmark can report a measured
number of network calls rather than a promise.
"""

from __future__ import annotations

import socket


class NetworkBlocked(RuntimeError):
    pass


class NetworkGuard:
    def __init__(self) -> None:
        self.attempts = 0
        self._saved = {}

    def _block(self, *args, **kwargs):
        self.attempts += 1
        raise NetworkBlocked("lulus.ai runs offline: outbound network access is blocked during a check.")

    def __enter__(self) -> "NetworkGuard":
        self._saved = {
            "connect": socket.socket.connect,
            "connect_ex": socket.socket.connect_ex,
            "create_connection": socket.create_connection,
        }
        socket.socket.connect = lambda s, *a, **k: self._block()
        socket.socket.connect_ex = lambda s, *a, **k: self._block()
        socket.create_connection = lambda *a, **k: self._block()
        return self

    def __exit__(self, *exc) -> None:
        socket.socket.connect = self._saved["connect"]
        socket.socket.connect_ex = self._saved["connect_ex"]
        socket.create_connection = self._saved["create_connection"]
