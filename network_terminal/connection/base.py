"""Contrato común de un transporte interactivo (SSH o Telnet)."""

from __future__ import annotations

import abc


class BaseConnection(abc.ABC):
    name = "base"
    default_newline = "\n"

    def __init__(self, host: str, port: int, *, connect_timeout: float = 10.0):
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout

    @abc.abstractmethod
    def connect(self) -> None: ...

    @abc.abstractmethod
    def send(self, data: str) -> None: ...

    @abc.abstractmethod
    def read(self) -> str:
        """Texto disponible ahora mismo (no bloqueante). Devuelve '' si no hay nada."""

    @abc.abstractmethod
    def is_alive(self) -> bool: ...

    @abc.abstractmethod
    def close(self) -> None: ...

    def send_line(self, line: str) -> None:
        self.send(line + self.default_newline)
