from __future__ import annotations

from .base import Device
from .parsers import parse_mikrotik_print_detail

_PRINT_SECTIONS = {
    "interfaces": "/interface print detail without-paging",
    "interfaces_ethernet": "/interface ethernet print detail without-paging",
    "ip_addresses": "/ip address print detail without-paging",
    "routes": "/ip route print detail without-paging",
    "vlans": "/interface vlan print detail without-paging",
    "firewall_filter": "/ip firewall filter print detail without-paging",
    "firewall_nat": "/ip firewall nat print detail without-paging",
}


class MikroTikDevice(Device):
    name = "MikroTik"
    vendor = "MikroTik"

    def running_config_command(self) -> str:
        return "/export"

    def collection_commands(self) -> dict[str, str]:
        return dict(_PRINT_SECTIONS)

    def parse_section(self, key: str, text: str):
        if key in _PRINT_SECTIONS:
            return parse_mikrotik_print_detail(text)
        return super().parse_section(key, text)

    def postprocess(self, facts: dict) -> None:
        # Fusiona datos de '/interface ethernet' (speed, poe) en 'interfaces'.
        eth = {
            e.get("name"): e
            for e in facts.get("interfaces_ethernet", [])
            if e.get("name")
        }
        for itf in facts.get("interfaces", []):
            extra = eth.get(itf.get("name"))
            if not extra:
                continue
            for field in (
                "speed",
                "poe-out",
                "poe-in",
                "auto-negotiation",
                "full-duplex",
                "sfp-shutdown-temperature",
            ):
                if field in extra and field not in itf:
                    itf[field] = extra[field]
        facts.pop("interfaces_ethernet", None)  # ya fusionado (queda en 'raw')

        routes = facts.get("routes", [])
        gateways = [
            r.get("gateway")
            for r in routes
            if r.get("dst-address") in ("0.0.0.0/0", "::/0") and r.get("gateway")
        ]
        addresses = [
            a.get("address") for a in facts.get("ip_addresses", []) if a.get("address")
        ]
        facts["summary"] = {
            "default_gateway": gateways[0] if gateways else None,
            "ip_addresses": addresses,
            "interface_count": len(facts.get("interfaces", [])),
            "vlan_count": len(facts.get("vlans", [])),
        }
