"""Cliente Telnet mínimo sobre socket, sin dependencias externas.

``telnetlib`` fue eliminado de la biblioteca estándar en Python 3.13, por eso se
implementa aquí una negociación IAC básica. Estrategia: rechazar todas las
opciones (WONT/DONT) para que el equipo caiga a modo línea, suficiente para una
CLI interactiva en esta primera versión.
"""

from __future__ import annotations

import logging
import socket
import time

from ..core.errors import (
    ConnectFailedError,
    ConnectTimeoutError,
    HostInvalidError,
    PortClosedError,
)
from .base import BaseConnection

log = logging.getLogger(__name__)

IAC = 255
DONT = 254
DO = 253
WONT = 252
WILL = 251
SB = 250
SE = 240


class TelnetConnection(BaseConnection):
    name = "telnet"
    default_newline = "\r\n"

    def __init__(self, host: str, port: int = 23, *, connect_timeout: float = 10.0):
        super().__init__(host, port, connect_timeout=connect_timeout)
        self._sock: socket.socket | None = None

    def connect(self) -> None:
        try:
            self._sock = socket.create_connection(
                (self.host, self.port), timeout=self.connect_timeout
            )
        except socket.gaierror as exc:
            raise HostInvalidError(str(exc)) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise ConnectTimeoutError(str(exc)) from exc
        except ConnectionRefusedError as exc:
            raise PortClosedError(str(exc)) from exc
        except OSError as exc:
            raise ConnectFailedError(str(exc)) from exc
        self._sock.setblocking(False)
        log.info("telnet: conexión TCP establecida con %s:%s", self.host, self.port)

    def _negotiate(self, data: bytes) -> bytes:
        """Filtra las secuencias IAC y responde rechazando opciones.
        Devuelve solo el texto plano."""
        out = bytearray()
        i, n = 0, len(data)
        while i < n:
            byte = data[i]
            if byte != IAC:
                out.append(byte)
                i += 1
                continue
            if i + 1 >= n:
                break  # secuencia incompleta
            cmd = data[i + 1]
            if cmd == IAC:  # 0xFF escapado -> byte literal
                out.append(IAC)
                i += 2
            elif cmd in (DO, DONT, WILL, WONT):
                if i + 2 >= n:
                    break
                self._respond_option(cmd, data[i + 2])
                i += 3
            elif cmd == SB:
                end = data.find(bytes([IAC, SE]), i)
                i = end + 2 if end != -1 else n
            else:
                i += 2
        return bytes(out)

    def _respond_option(self, cmd: int, opt: int) -> None:
        if cmd == DO:
            reply = WONT
        elif cmd == WILL:
            reply = DONT
        else:
            return  # ya es un WONT/DONT del otro extremo
        try:
            self._sock.sendall(bytes([IAC, reply, opt]))
        except OSError:
            pass

    def send(self, data: str) -> None:
        if not self._sock:
            raise ConnectFailedError("socket no inicializado")
        payload = data.encode("utf-8", "replace").replace(bytes([IAC]), bytes([IAC, IAC]))
        try:
            self._sock.sendall(payload)
        except OSError as exc:
            raise ConnectFailedError(str(exc)) from exc

    def read(self) -> str:
        if not self._sock:
            return ""
        try:
            chunk = self._sock.recv(65535)
        except (BlockingIOError, InterruptedError):
            return ""
        except OSError:
            return ""
        if not chunk:
            return ""
        return self._negotiate(chunk).decode("utf-8", "replace")

    def is_alive(self) -> bool:
        return self._sock is not None

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            finally:
                self._sock = None
            log.info("telnet: conexión cerrada (%s:%s)", self.host, self.port)

    def login(
        self, username: str, password: str, *, timeout: float = 12.0, on_text=None
    ) -> None:
        """Login best-effort: detecta los prompts habituales y responde.
        Si no los reconoce, se continúa en modo manual. La contraseña nunca se loguea."""
        deadline = time.time() + timeout
        stage = "user"
        while time.time() < deadline:
            text = self.read()
            if text and on_text:
                on_text(text)
            low = text.lower()
            if stage == "user" and any(k in low for k in ("login:", "username:", "user:")):
                self.send_line(username)
                log.info("telnet: usuario enviado")
                stage = "pass"
            elif stage == "pass" and "password" in low:
                self.send(password + self.default_newline)
                log.info("telnet: contraseña enviada")
                return
            time.sleep(0.2)
        log.info("telnet: sin prompt de login automático; se continúa en modo manual")
