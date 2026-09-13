"""Validación de entradas y saneado de nombres de archivo."""

from __future__ import annotations

import ipaddress
import re

from .errors import HostInvalidError

DEFAULT_PORTS = {"ssh": 22, "telnet": 23}

_HOSTNAME_LABEL = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def default_port_for(protocol: str) -> int:
    return DEFAULT_PORTS.get((protocol or "").strip().lower(), 22)


def validate_host(value: str) -> str:
    """Devuelve el host normalizado o lanza ``HostInvalidError``."""
    host = (value or "").strip()
    if not host or len(host) > 253 or any(c.isspace() for c in host):
        raise HostInvalidError(f"host vacío o con formato inválido (len={len(host)})")
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    labels = host.rstrip(".").split(".")
    if all(_HOSTNAME_LABEL.match(label) for label in labels):
        return host
    raise HostInvalidError("no es una IP ni un hostname válido")


def validate_port(value) -> int:
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError("Puerto inválido.")
    if not 1 <= port <= 65535:
        raise ValueError("Puerto inválido.")
    return port


def sanitize_filename_component(
    value: str, *, max_len: int = 80, fallback: str = "device"
) -> str:
    """Convierte un texto arbitrario en un componente de nombre de archivo seguro."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    cleaned = re.sub(r"_{2,}", "_", cleaned).strip("._")
    cleaned = cleaned[:max_len].strip("._")
    if not cleaned:
        return fallback
    if cleaned.upper() in _WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned
