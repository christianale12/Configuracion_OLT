from __future__ import annotations

from .base import Device
from .parsers import parse_table


class ZteOltDevice(Device):
    """OLT ZTE (familia zxros / C3xx).

    La salida estructurada de ZTE varía mucho según modelo y firmware, así que
    este driver es *scaffolding*: define el conjunto de comandos y guarda
    ``raw_lines`` por sección; solo parsea lo de formato tabular estable
    (``show ip interface brief``). Ajustar comandos y parsers contra el equipo real.
    """

    name = "ZTE OLT"
    vendor = "ZTE"

    def prepare_commands(self) -> list[str]:
        # En zxros suele servir para desactivar la paginación (--More--).
        return ["terminal length 0"]

    def running_config_command(self) -> str:
        return "show running-config"

    def collection_commands(self) -> dict[str, str]:
        return {
            "interfaces": "show interface",
            "ip_interface_brief": "show ip interface brief",
            "ip_interface": "show ip interface",
            "routes": "show ip route",
            "vlans": "show vlan",
            "gpon_onu_state": "show gpon onu state",
            "running_config": "show running-config",
        }

    def parse_section(self, key: str, text: str):
        if key == "ip_interface_brief":
            return parse_table(text)
        return super().parse_section(key, text)
