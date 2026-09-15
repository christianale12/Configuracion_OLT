"""Dobles de prueba (no tocan la red)."""

from __future__ import annotations

from ..connection.base import BaseConnection


class FakeConnection(BaseConnection):
    name = "fake"

    def __init__(self, script=None):
        super().__init__("fake-host", 0)
        self.sent: list[str] = []
        self._script = list(script or [])
        self._alive = False

    def connect(self) -> None:
        self._alive = True

    def send(self, data: str) -> None:
        self.sent.append(data)

    def read(self) -> str:
        return self._script.pop(0) if self._script else ""

    def is_alive(self) -> bool:
        return self._alive

    def close(self) -> None:
        self._alive = False


class ScriptedConnection(BaseConnection):
    """Conexión falsa que responde según el comando recibido.

    ``responses`` mapea ``comando -> texto de salida``; los comandos no mapeados
    devuelven ``default``. La respuesta se entrega una sola vez (el siguiente
    ``read()`` devuelve '').
    """

    name = "fake"

    def __init__(self, responses=None, default: str = ""):
        super().__init__("fake-host", 0)
        self.responses = dict(responses or {})
        self.default = default
        self.sent: list[str] = []
        self._pending = ""
        self._alive = False

    def connect(self) -> None:
        self._alive = True

    def send(self, data: str) -> None:
        self.sent.append(data)
        cmd = data.strip()
        if cmd:
            self._pending = self.responses.get(cmd, self.default)

    def read(self) -> str:
        out, self._pending = self._pending, ""
        return out

    def is_alive(self) -> bool:
        return self._alive

    def close(self) -> None:
        self._alive = False


class FakeSocket:
    def __init__(self):
        self.sent = bytearray()

    def sendall(self, data: bytes) -> None:
        self.sent.extend(data)
