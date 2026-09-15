from __future__ import annotations

from .base import Device
from .parsers import parse_table


class CiscoDevice(Device):
    name = "Cisco IOS"
    vendor = "Cisco"

    def prepare_commands(self) -> list[str]:
        return ["terminal length 0"]

    def running_config_command(self) -> str:
        return "show running-config"

    def collection_commands(self) -> dict[str, str]:
        return {
            "interfaces": "show interfaces",
            "ip_interface_brief": "show ip interface brief",
            "routes": "show ip route",
            "vlans": "show vlan brief",
            "running_config": "show running-config",
        }

    def parse_section(self, key: str, text: str):
        if key == "ip_interface_brief":
            return parse_table(text)
        return super().parse_section(key, text)
