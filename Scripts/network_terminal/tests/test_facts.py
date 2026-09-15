import unittest

import yaml

from network_terminal.devices.facts import collect_device_facts
from network_terminal.devices.mikrotik import MikroTikDevice
from network_terminal.devices.zte_olt import ZteOltDevice

MTK = {
    "/interface print detail without-paging": (
        'Flags: R - running\n'
        ' 0 R name="ether1" type="ether" mtu=1500 comment="WAN"\n'
        ' 1 R name="ether2" type="ether" mtu=1500\n'
    ),
    "/interface ethernet print detail without-paging": (
        ' 0 name="ether1" speed=100 poe-out=false\n'
        ' 1 name="ether2" speed=1000 poe-out=false\n'
    ),
    "/ip address print detail without-paging": (
        " 0 address=192.168.1.1/24 network=192.168.1.0 interface=ether1\n"
    ),
    "/ip route print detail without-paging": (
        " 0 A S dst-address=0.0.0.0/0 gateway=192.168.1.254\n"
        " 1 A dst-address=192.168.1.0/24 gateway=ether1\n"
    ),
    "/interface vlan print detail without-paging": (
        ' 0 name="vlan100" vlan-id=100 interface=ether1\n'
    ),
    "/ip firewall filter print detail without-paging": (
        " 0 chain=input action=accept protocol=icmp\n"
    ),
    "/ip firewall nat print detail without-paging": (
        " 0 chain=srcnat action=masquerade out-interface=ether1\n"
    ),
}


def mtk_runner(cmd):
    return MTK.get(cmd, "")


class MikrotikFactsTests(unittest.TestCase):
    def test_collect_structured(self):
        facts = collect_device_facts(
            MikroTikDevice(), mtk_runner, host="10.0.0.1", protocol="ssh"
        )
        self.assertEqual(facts["device"]["vendor"], "MikroTik")
        self.assertEqual(facts["device"]["host"], "10.0.0.1")
        self.assertEqual(len(facts["interfaces"]), 2)

        ether1 = next(i for i in facts["interfaces"] if i["name"] == "ether1")
        self.assertEqual(ether1["speed"], 100)  # fusionado desde 'ethernet'
        self.assertIs(ether1["poe-out"], False)
        self.assertNotIn("interfaces_ethernet", facts)  # fusionado y removido

        self.assertEqual(facts["summary"]["default_gateway"], "192.168.1.254")
        self.assertEqual(facts["summary"]["ip_addresses"], ["192.168.1.1/24"])
        self.assertEqual(facts["summary"]["vlan_count"], 1)

        self.assertIn("raw", facts)
        self.assertIn("interfaces", facts["raw"])

    def test_yaml_roundtrip(self):
        facts = collect_device_facts(MikroTikDevice(), mtk_runner, host="h")
        text = yaml.safe_dump(facts, sort_keys=False, allow_unicode=True)
        back = yaml.safe_load(text)
        self.assertEqual(back["interfaces"][0]["name"], "ether1")
        self.assertEqual(back["device"]["type"], "MikroTik")

    def test_include_raw_false(self):
        facts = collect_device_facts(
            MikroTikDevice(), mtk_runner, host="h", include_raw=False
        )
        self.assertNotIn("raw", facts)
        self.assertIn("interfaces", facts)


class ZteFactsTests(unittest.TestCase):
    def test_error_isolated_per_section(self):
        def runner(cmd):
            if "route" in cmd:
                raise RuntimeError("timeout")
            return "col-a col-b\nval-1 val-2\n"

        facts = collect_device_facts(
            ZteOltDevice(), runner, host="olt1", protocol="telnet"
        )
        self.assertEqual(facts["device"]["vendor"], "ZTE")
        self.assertIn("errors", facts)
        self.assertIn("routes", facts["errors"])
        self.assertIn("interfaces", facts)  # el resto de secciones sí se recolecta


if __name__ == "__main__":
    unittest.main()
