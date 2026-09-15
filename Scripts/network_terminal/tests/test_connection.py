import unittest

from network_terminal.connection.manager import ConnectionManager, ConnectionParams
from network_terminal.connection.ssh_client import SshConnection
from network_terminal.connection.telnet_client import TelnetConnection
from network_terminal.core.errors import TerminalError


class BuildConnectionTests(unittest.TestCase):
    def setUp(self):
        self.mgr = ConnectionManager()

    def test_ssh_selected(self):
        params = ConnectionParams(
            host="10.0.0.1", port=22, protocol="ssh", username="u", password="p"
        )
        self.assertIsInstance(self.mgr._build_connection(params), SshConnection)

    def test_telnet_selected(self):
        params = ConnectionParams(host="10.0.0.1", port=23, protocol="telnet")
        self.assertIsInstance(self.mgr._build_connection(params), TelnetConnection)

    def test_unsupported_protocol(self):
        params = ConnectionParams(host="10.0.0.1", port=80, protocol="http")
        with self.assertRaises(TerminalError):
            self.mgr._build_connection(params)

    def test_default_state(self):
        self.assertEqual(self.mgr.state, "disconnected")
        self.assertFalse(self.mgr.is_connected())


class SecretHandlingTests(unittest.TestCase):
    def test_password_not_in_repr(self):
        conn = SshConnection("10.0.0.1", 22, username="u", password="s3cr3t")
        self.assertNotIn("s3cr3t", repr(conn))


if __name__ == "__main__":
    unittest.main()
