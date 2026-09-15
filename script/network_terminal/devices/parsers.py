"""Parsers de salida de CLI a estructuras Python.

Son *best-effort*: si algo no encaja, se devuelve el texto en bruto (``raw_lines``)
y nunca se lanza una excepción hacia arriba desde la recolección.
"""

from __future__ import annotations

import re

# key=value  /  key="valor con espacios"
_KV = re.compile(r'([^\s=]+)=("([^"]*)"|\S*)')

# línea que abre un registro en '... print detail' de RouterOS:
#   " 3  RS name=... "  /  " 0 A S dst-address=... "
#   -> índice + flags opcionales (una o varias letras, quizá separadas) + primer key=value
_INDEX_LINE = re.compile(r"^\s*(\d+)\s+((?:[A-Za-z]{1,3}\s+)*)(\S+=.*)$")


def _coerce(value: str):
    low = value.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def _pairs(blob: str) -> dict:
    out: dict = {}
    for key, rawval, quoted in _KV.findall(blob):
        out[key] = _coerce(quoted if rawval.startswith('"') else rawval)
    return out


def parse_mikrotik_print_detail(text: str) -> list[dict]:
    """Convierte la salida de ``... print detail`` (RouterOS) en una lista de dicts.

    Soporta: la línea ``Flags: ...`` de leyenda, registros que empiezan con un
    índice numérico y flags de 1–6 letras, pares ``key=value`` y
    ``key="valor con espacios"``, y líneas de continuación indentadas.
    """
    records: list[dict] = []
    pending: dict | None = None  # {"index": int, "flags": str, "blob": str}

    def finalize(p: dict) -> dict:
        rec: dict = {"_index": p["index"]}
        if p["flags"]:
            rec["_flags"] = p["flags"]
        rec.update(_pairs(p["blob"]))
        return rec

    for line in text.splitlines():
        if not line.strip() or line.lstrip().lower().startswith("flags:"):
            continue
        m = _INDEX_LINE.match(line)
        if m:
            if pending is not None:
                records.append(finalize(pending))
            pending = {
                "index": int(m.group(1)),
                "flags": " ".join((m.group(2) or "").split()),
                "blob": m.group(3),
            }
        elif pending is not None and "=" in line:
            pending["blob"] += " " + line.strip()

    if pending is not None:
        records.append(finalize(pending))
    return records


def parse_table(text: str) -> list[dict]:
    """Parser genérico de tablas 'columna alineada por espacios' (p. ej.
    ``show ip interface brief``). Si una fila no tiene el mismo número de
    columnas que el encabezado, se guarda como ``{"_raw": "<línea>"}``.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    header = lines[0].split()
    if len(header) < 2:
        return []
    rows: list[dict] = []
    for ln in lines[1:]:
        cells = ln.split()
        if len(cells) < 2:
            continue
        if len(cells) == len(header):
            rows.append(dict(zip(header, cells)))
        else:
            rows.append({"_raw": ln.strip()})
    return rows
