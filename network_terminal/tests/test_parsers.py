import unittest

from network_terminal.devices.parsers import parse_mikrotik_print_detail, parse_table

IFACE = """Flags: X - disabled, R - running, S - slave
 0  R  name="ether1" default-name="ether1" type="ether" mtu=1500 comment="WAN uplink"
       mac-address=CC:2D:E0:00:00:01
 1  RS name="ether2" type="ether" mtu=1500 disabled=false
 2     name="bridge1" type="bridge" mtu=1500 disabled=true
"""

ADDR = """Flags: X - disabled, I - invalid, D - dynamic
 0   address=192.168.88.1/24 network=192.168.88.0 interface=bridge1 actual-interface=bridge1
 1 D address=10.0.0.5/24 network=10.0.0.0 interface=ether1
"""


class MikrotikDetailTests(unittest.TestCase):
    def test_interfaces(self):
        recs = parse_mikrotik_print_detail(IFACE)
        self.assertEqual(len(recs), 3)
        self.assertEqual(recs[0]["name"], "ether1")
        self.assertEqual(recs[0]["_flags"], "R")
        self.assertEqual(recs[0]["mtu"], 1500)
        self.assertEqual(recs[0]["comment"], "WAN uplink")
        self.assertEqual(recs[0]["mac-address"], "CC:2D:E0:00:00:01")  # continuación
        self.assertEqual(recs[1]["_flags"], "RS")
        self.assertIs(recs[1]["disabled"], False)
        self.assertIs(recs[2]["disabled"], True)
        self.assertNotIn("_flags", recs[2])

    def test_addresses(self):
        recs = parse_mikrotik_print_detail(ADDR)
        self.assertEqual(recs[0]["address"], "192.168.88.1/24")
        self.assertEqual(recs[0]["interface"], "bridge1")
        self.assertEqual(recs[1]["_flags"], "D")
        self.assertEqual(recs[1]["address"], "10.0.0.5/24")

    def test_empty(self):
        self.assertEqual(parse_mikrotik_print_detail(""), [])


class TableTests(unittest.TestCase):
    def test_brief(self):
        text = (
            "Interface IP-Address OK Method Status Protocol\n"
            "gei_1/1 10.0.0.1 YES manual up up\n"
            "gei_1/2 unassigned YES unset down down\n"
        )
        rows = parse_table(text)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Interface"], "gei_1/1")
        self.assertEqual(rows[0]["IP-Address"], "10.0.0.1")
        self.assertEqual(rows[1]["Status"], "down")

    def test_too_short(self):
        self.assertEqual(parse_table("solo una linea"), [])


if __name__ == "__main__":
    unittest.main()
