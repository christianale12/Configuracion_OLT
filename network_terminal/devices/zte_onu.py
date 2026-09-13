from __future__ import annotations

from .base import Device


class ZteOnuDevice(Device):
    """ONU/ONT ZTE administrada por su propia CLI (Telnet/SSH directo al equipo).

    Aviso: muchas ONU se administran *a través de la OLT*, no por conexión
    directa. Este driver es para las que exponen CLI propia. Parsing best-effort
    (guarda ``raw_lines``); ajustar comandos contra el equipo real.
    """

    name = "ZTE ONU (CLI)"
    vendor = "ZTE"

    def running_config_command(self) -> str:
        return "show running-config"

    def collection_commands(self) -> dict[str, str]:
        return {
            "interfaces": "show interface",
            "ip": "show ip",
            "vlans": "show vlan",
            "running_config": "show running-config",
        }
