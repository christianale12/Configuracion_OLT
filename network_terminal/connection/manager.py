"""Gestión del ciclo de vida de una conexión y de su hilo lector.

La GUI nunca toca sockets: llama a estos métodos y consume ``poll_output()``.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass

from ..core.errors import TerminalError
from ..core.validation import validate_host, validate_port
from .ssh_client import SshConnection
from .telnet_client import TelnetConnection

log = logging.getLogger(__name__)


@dataclass
class ConnectionParams:
    host: str
    port: int
    protocol: str  # "ssh" | "telnet"
    username: str = ""
    password: str = ""  # solo en memoria
    trust_new_host_key: bool = False
    connect_timeout: float = 10.0


class ConnectionManager:
    def __init__(self):
        self._conn = None
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._out: queue.Queue[str] = queue.Queue()
        self._state = "disconnected"
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        return self._state

    def is_connected(self) -> bool:
        return (
            self._state == "connected"
            and self._conn is not None
            and self._conn.is_alive()
        )

    # ---------- conexión ----------
    def connect_async(self, params: ConnectionParams, on_success, on_error) -> None:
        threading.Thread(
            target=self._connect_worker,
            args=(params, on_success, on_error),
            daemon=True,
        ).start()

    def _build_connection(self, params: ConnectionParams):
        if params.protocol == "ssh":
            return SshConnection(
                params.host,
                params.port,
                username=params.username,
                password=params.password,
                connect_timeout=params.connect_timeout,
                trust_new_host_key=params.trust_new_host_key,
            )
        if params.protocol == "telnet":
            return TelnetConnection(
                params.host, params.port, connect_timeout=params.connect_timeout
            )
        raise TerminalError(
            f"protocolo no soportado: {params.protocol!r}",
            user_message="Protocolo no soportado.",
        )

    def _connect_worker(self, params: ConnectionParams, on_success, on_error) -> None:
        try:
            validate_host(params.host)
            validate_port(params.port)
            self._state = "connecting"
            log.info(
                "conexión iniciada: %s %s:%s usuario=%s",
                params.protocol,
                params.host,
                params.port,
                params.username or "(vacío)",
            )
            conn = self._build_connection(params)
            conn.connect()

            if params.protocol == "telnet" and (params.username or params.password):
                conn.login(params.username, params.password, on_text=self._out.put)

            with self._lock:
                self._conn = conn
                self._stop.clear()
                self._pause.clear()
                self._state = "connected"
                self._reader = threading.Thread(target=self._read_loop, daemon=True)
                self._reader.start()
            log.info("conexión exitosa: %s:%s", params.host, params.port)
            on_success()
        except TerminalError as exc:
            self._state = "disconnected"
            log.warning(
                "conexión fallida: %s | detalle: %s", exc.user_message, exc.detail
            )
            on_error(exc)
        except Exception as exc:  # cualquier fallo inesperado: la app no debe caerse
            self._state = "disconnected"
            log.exception("conexión fallida (error inesperado)")
            on_error(
                TerminalError(
                    str(exc), user_message="No se pudo conectar con el equipo."
                )
            )

    # ---------- lectura ----------
    def _read_loop(self) -> None:
        conn = self._conn
        try:
            while not self._stop.is_set() and conn and conn.is_alive():
                if self._pause.is_set():
                    time.sleep(0.05)
                    continue
                data = conn.read()
                if data:
                    self._out.put(data)
                else:
                    time.sleep(0.05)
        except Exception:
            log.exception("lector: error leyendo del equipo")
        finally:
            if not self._stop.is_set():
                self._out.put("\r\n[sesión finalizada por el equipo]\r\n")
            self._state = "disconnected"

    @contextmanager
    def _reader_paused(self):
        self._pause.set()
        time.sleep(0.15)  # deja terminar una iteración de lectura en curso
        try:
            yield
        finally:
            self._pause.clear()

    # ---------- envío ----------
    def send(self, text: str) -> None:
        if not self.is_connected():
            raise TerminalError("sin conexión", user_message="No hay conexión activa.")
        self._conn.send(text)

    def send_line(self, line: str) -> None:
        if not self.is_connected():
            raise TerminalError("sin conexión", user_message="No hay conexión activa.")
        self._conn.send_line(line)
        log.info("comando ejecutado: %s", line[:200])

    def poll_output(self) -> str:
        parts = []
        try:
            while True:
                parts.append(self._out.get_nowait())
        except queue.Empty:
            pass
        return "".join(parts)

    # ---------- captura de configuración ----------
    def capture_config(
        self,
        device,
        *,
        quiet_after: float = 2.0,
        overall_timeout: float = 60.0,
        on_progress=None,
    ) -> str:
        if not self.is_connected():
            raise TerminalError("sin conexión", user_message="No hay conexión activa.")
        conn = self._conn
        with self._reader_paused():
            conn.read()  # descarta lo pendiente
            for cmd in device.prepare_commands():
                conn.send_line(cmd)
                time.sleep(0.4)
                conn.read()
            command = device.running_config_command()
            conn.send_line(command)
            log.info("comando ejecutado: %s", command)
            chunks: list[str] = []
            start = last = time.time()
            while time.time() - start < overall_timeout:
                data = conn.read()
                if data:
                    chunks.append(data)
                    if on_progress:
                        on_progress(data)
                    last = time.time()
                elif chunks and time.time() - last >= quiet_after:
                    break
                else:
                    time.sleep(0.1)
        text = "".join(chunks)
        log.info("configuración obtenida (%d caracteres)", len(text))
        return text

    def run_capture(
        self,
        command: str,
        *,
        quiet_after: float = 1.5,
        overall_timeout: float = 45.0,
    ) -> str:
        """Ejecuta un comando en la sesión viva y devuelve su salida completa.
        Pausa el hilo lector mientras dura la captura (evita carreras)."""
        if not self.is_connected():
            raise TerminalError("sin conexión", user_message="No hay conexión activa.")
        conn = self._conn
        with self._reader_paused():
            conn.read()  # descarta lo pendiente
            conn.send_line(command)
            log.info("comando ejecutado: %s", command[:200])
            chunks: list[str] = []
            start = last = time.time()
            while time.time() - start < overall_timeout:
                data = conn.read()
                if data:
                    chunks.append(data)
                    last = time.time()
                elif chunks and time.time() - last >= quiet_after:
                    break
                else:
                    time.sleep(0.1)
        return "".join(chunks)

    # ---------- cierre ----------
    def disconnect(self) -> None:
        self._stop.set()
        with self._lock:
            conn, self._conn = self._conn, None
        if conn:
            conn.close()
        if self._reader and self._reader.is_alive():
            self._reader.join(timeout=2.0)
        self._reader = None
        if self._state != "disconnected":
            log.info("desconexión solicitada por el usuario")
        self._state = "disconnected"
