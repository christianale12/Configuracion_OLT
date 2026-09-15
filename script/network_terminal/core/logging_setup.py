"""Configuración de logging básico."""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_DIR = Path.home() / ".network_terminal"
LOG_DIR = APP_DIR / "logs"

_SECRET_PATTERNS = [
    re.compile(r"(password\s*=\s*)(\S+)", re.IGNORECASE),
    re.compile(r"(passwd\s+)(\S+)", re.IGNORECASE),
    re.compile(r"(secret\s+)(\S+)", re.IGNORECASE),
]


class SecretRedactingFilter(logging.Filter):
    """Defensa en profundidad: si algún secreto se cuela en un mensaje
    (p. ej. un comando ``/user add password=...``), se enmascara antes de escribir."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern in _SECRET_PATTERNS:
            msg = pattern.sub(r"\1***", msg)
        record.msg = msg
        record.args = ()
        return True


def configure_logging(level: int = logging.INFO) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "network_terminal.log"

    root = logging.getLogger()
    if getattr(root, "_network_terminal_configured", False):
        return log_file

    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    redactor = SecretRedactingFilter()

    file_handler = RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.addFilter(redactor)
    root.addHandler(file_handler)

    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        console.addFilter(redactor)
        root.addHandler(console)

    root._network_terminal_configured = True
    return log_file
