import unittest

from network_terminal.core import validation as v
from network_terminal.core.errors import HostInvalidError


class HostTests(unittest.TestCase):
    def test_valid_ipv4(self):
        self.assertEqual(v.validate_host(" 192.168.1.1 "), "192.168.1.1")

    def test_valid_ipv6(self):
        self.assertEqual(v.validate_host("::1"), "::1")

    def test_valid_hostname(self):
        self.assertEqual(v.validate_host("router-1.lab.local"), "router-1.lab.local")

    def test_empty(self):
        with self.assertRaises(HostInvalidError):
            v.validate_host("")

    def test_spaces(self):
        with self.assertRaises(HostInvalidError):
            v.validate_host("192.168 .1.1")

    def test_bad_hostname(self):
        with self.assertRaises(HostInvalidError):
            v.validate_host("bad_host!name")


class PortTests(unittest.TestCase):
    def test_ok_str(self):
        self.assertEqual(v.validate_port("22"), 22)

    def test_ok_int(self):
        self.assertEqual(v.validate_port(65535), 65535)

    def test_zero(self):
        with self.assertRaises(ValueError):
            v.validate_port(0)

    def test_too_high(self):
        with self.assertRaises(ValueError):
            v.validate_port(70000)

    def test_not_a_number(self):
        with self.assertRaises(ValueError):
            v.validate_port("ssh")

    def test_defaults(self):
        self.assertEqual(v.default_port_for("ssh"), 22)
        self.assertEqual(v.default_port_for("telnet"), 23)
        self.assertEqual(v.default_port_for("otro"), 22)


class SanitizeTests(unittest.TestCase):
    def test_keeps_ip(self):
        self.assertEqual(v.sanitize_filename_component("192.168.1.1"), "192.168.1.1")

    def test_replaces_separators(self):
        self.assertEqual(v.sanitize_filename_component("a/b\\c:d"), "a_b_c_d")

    def test_empty_fallback(self):
        self.assertEqual(v.sanitize_filename_component("   "), "device")

    def test_windows_reserved(self):
        self.assertEqual(v.sanitize_filename_component("CON"), "_CON")

    def test_max_length(self):
        self.assertLessEqual(len(v.sanitize_filename_component("x" * 200)), 80)


if __name__ == "__main__":
    unittest.main()
