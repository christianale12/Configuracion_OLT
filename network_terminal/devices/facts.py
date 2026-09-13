"""Recolección de información estructurada de un equipo -> dict listo para YAML.

``collect_device_facts`` recibe un ``device`` (para saber qué comandos correr y
cómo parsear cada sección) y un ``run_command(cmd) -> str`` (para ejecutarlos).
Así funciona igual con una sesión interactiva (``ConnectionManager.run_capture``)
o con la descarga masiva (``Device.execute``).
"""

from __future__ import annotations

import logging
from datetime import datetime

log = logging.getLogger(__name__)

# Orden preferido de las secciones en el YAML final (las que existan).
SECTION_ORDER = [
    "interfaces",
    "ip_addresses",
    "ip_interface_brief",
    "ip_interface",
    "ip",
    "routes",
    "vlans",
    "firewall_filter",
    "firewall_nat",
    "acls",
    "gpon_onu_state",
    "summary",
    "running_config",
]

_EMPTY = (None, [], {}, "")


def collect_device_facts(
    device,
    run_command,
    *,
    host: str = "",
    protocol: str = "",
    include_raw: bool = True,
) -> dict:
    started = datetime.now()
    device_meta = {
        "host": host,
        "type": device.name,
        "vendor": getattr(device, "vendor", "") or "",
        "model": getattr(device, "model", "") or "",
        "protocol": protocol,
        "collected_at": started.isoformat(timespec="seconds"),
        "tool": "network_terminal",
    }
    facts: dict = {"device": device_meta}
    raw: dict = {}
    errors: dict = {}

    for prep in device.prepare_commands():
        try:
            run_command(prep)
        except Exception:  # preparación best-effort, no crítica
            log.debug("facts: preparación %r falló", prep, exc_info=True)

    for key, command in device.collection_commands().items():
        try:
            text = run_command(command)
        except Exception as exc:
            errors[key] = f"comando: {exc}"
            log.warning("facts: %s: fallo al ejecutar %r: %s", host or "?", command, exc)
            continue
        if include_raw:
            raw[key] = text
        try:
            parsed = device.parse_section(key, text)
        except Exception as exc:
            errors[key] = f"parse: {exc}"
            parsed = {"raw_lines": text.splitlines()}
        if parsed not in _EMPTY:
            facts[key] = parsed

    try:
        device.postprocess(facts)
    except Exception as exc:
        errors["postprocess"] = str(exc)
        log.warning("facts: postprocess falló: %s", exc)

    if errors:
        facts["errors"] = errors
    if include_raw:
        facts["raw"] = raw

    # Reordenar para un YAML legible: device -> secciones conocidas -> resto -> raw.
    ordered: dict = {"device": facts["device"]}
    for k in SECTION_ORDER:
        if k in facts and k != "device":
            ordered[k] = facts[k]
    for k, v in facts.items():
        if k not in ordered and k != "raw":
            ordered[k] = v
    if "raw" in facts:
        ordered["raw"] = facts["raw"]
    log.info(
        "facts: %s -> %d sección(es), %d aviso(s)",
        host or "?",
        sum(1 for k in ordered if k not in ("device", "raw", "errors")),
        len(errors),
    )
    return ordered
