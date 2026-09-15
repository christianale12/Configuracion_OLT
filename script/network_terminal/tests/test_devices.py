import unittest

from network_terminal.devices.cisco import CiscoDevice
from network_terminal.devices.generic import GenericDevice
from network_terminal.devices.mikrotik import MikroTikDevice
from network_terminal.devices.registry import DEVICE_TYPES, create_device
from network_terminal.devices.zte_olt import ZteOltDevice
from network_terminal.devices.zte_onu import ZteOnuDevice
from network_terminal.tests._fakes import FakeConnection


class CommandTests(unittest.TestCase):
    def test_mikrotik(self):
        self.assertEqual(MikroTikDevice().running_config_command(), "/export")

    def test_cisco(self):
        dev = CiscoDevice()
        self.assertEqual(dev.running_config_command(), "show running-config")
        self.assertIn("terminal length 0", dev.prepare_commands())

    def test_generic_default_and_custom(self):
        self.assertEqual(GenericDevice().running_config_command(), "show running-config")
        self.assertEqual(
            GenericDevice(config_command="display current-configuration").running_config_command(),
            "display current-configuration",
        )

    def test_zte_olt(self):
        dev = ZteOltDevice()
        self.assertEqual(dev.vendor, "ZTE")
        self.assertEqual(dev.running_config_command(), "show running-config")
        cmds = dev.collection_commands()
        self.assertIn("interfaces", cmds)
        self.assertIn("vlans", cmds)
        self.assertIn("gpon_onu_state", cmds)

    def test_zte_onu(self):
        dev = ZteOnuDevice()
        self.assertEqual(dev.vendor, "ZTE")
        self.assertIn("interfaces", dev.collection_commands())


class RegistryTests(unittest.TestCase):
    def test_types_present(self):
        self.assertIn("MikroTik", DEVICE_TYPES)
        self.assertIn("Cisco IOS", DEVICE_TYPES)
        self.assertIn("ZTE OLT", DEVICE_TYPES)
        self.assertIn("ZTE ONU (CLI)", DEVICE_TYPES)
        self.assertIn("Genérico", DEVICE_TYPES)

    def test_create_known(self):
        self.assertIsInstance(create_device("MikroTik", None), MikroTikDevice)

    def test_create_unknown(self):
        with self.assertRaises(ValueError):
            create_device("Nortel", None)


class ExecuteTests(unittest.TestCase):
    def test_execute_accumulates_and_sends_command(self):
        conn = FakeConnection(script=["Router#", "line-1\n", "line-2\n"])
        conn.connect()
        dev = GenericDevice(conn, config_command="show running-config")
        out = dev.execute(
            "show running-config", quiet_after=0.2, overall_timeout=3.0
        )
        self.assertIn("line-1", out)
        self.assertIn("line-2", out)
        self.assertTrue(any("show running-config" in s for s in conn.sent))


if __name__ == "__main__":
    unittest.main()
