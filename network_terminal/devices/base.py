"""Abstracción de dispositivo.

Envuelve una conexión y aporta el conocimiento específico del fabricante
(qué comando devuelve la configuración, qué preparación hace falta, etc.).
La GUI usa ``running_config_command()`` / ``prepare_commands()``; ``execute()`` y
``get_running_config()`` sirven para uso directo (y para los tests con conexiones
simuladas).
"""

from __future__ import annotations

import abc
import logging
import time

log = logging.getLogger(__name__)


class Device(abc.ABC):
    name = "generic"
    vendor = ""
    model = ""

    def __init__(self, connection=None):
        self.conn = connection

    def connect(self) -> None:
        self.conn.connect()

    def disconnect(self) -> None:
        self.conn.close()

    def prepare_commands(self) -> list[str]:
        """Comandos previos a la captura (p. ej. desactivar paginación)."""
        return []

    def execute(
        self, command: str, *, quiet_after: float = 1.0, overall_timeout: float = 30.0
    ) -> str:
        """Envía un comando y acumula la salida hasta que el equipo queda en
        silencio ``quiet_after`` s, o hasta ``overall_timeout`` s."""
        self.conn.send_line(command)
        chunks: list[str] = []
        start = last = time.time()
        while time.time() - start < overall_timeout:
            data = self.conn.read()
            if data:
                chunks.append(data)
                last = time.time()
            elif chunks and time.time() - last >= quiet_after:
                break
            elif not chunks and time.time() - start >= min(overall_timeout, 3.0):
                break  # silencio total: el equipo no respondió a este comando
            else:
                time.sleep(0.1)
        return "".join(chunks)

    @abc.abstractmethod
    def running_config_command(self) -> str: ...

    # ---- recolección estructurada (para exportar a YAML) ----
    def collection_commands(self) -> dict[str, str]:
        """Mapa ``clave_lógica -> comando`` que se ejecutan para armar los facts.
        Por defecto vacío: el equipo genérico solo expone la running-config."""
        return {}

    def parse_section(self, key: str, text: str):
        """Convierte la salida cruda de una sección en algo estructurado.
        Por defecto guarda las líneas tal cual."""
        return {"raw_lines": text.splitlines()}

    def postprocess(self, facts: dict) -> None:
        """Hook opcional: derivar campos (gateway, resumen, fusiones, etc.)."""
        return None

    def get_running_config(self) -> str:
        for cmd in self.prepare_commands():
            self.execute(cmd, quiet_after=0.5, overall_timeout=10.0)
        cfg = self.execute(
            self.running_config_command(), quiet_after=2.0, overall_timeout=60.0
        )
        log.info("configuración obtenida (%d caracteres)", len(cfg))
        return cfg
