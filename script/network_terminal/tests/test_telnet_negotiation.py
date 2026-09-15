import unittest

from network_terminal.connection.telnet_client import (
    DO,
    DONT,
    IAC,
    SB,
    SE,
    WILL,
    WONT,
    TelnetConnection,
)
from network_terminal.tests._fakes import FakeSocket


class NegotiationTests(unittest.TestCase):
    def setUp(self):
        self.tn = TelnetConnection("host", 23)
        self.sock = FakeSocket()
        self.tn._sock = self.sock

    def test_strips_iac_and_replies_rejecting(self):
        data = b"hi" + bytes([IAC, DO, 3]) + b"!" + bytes([IAC, WILL, 1])
        clean = self.tn._negotiate(data)
        self.assertEqual(clean, b"hi!")
        self.assertEqual(
            bytes(self.sock.sent), bytes([IAC, WONT, 3, IAC, DONT, 1])
        )

    def test_escaped_ff_is_literal(self):
        data = bytes([ord("a"), IAC, IAC, ord("b")])
        self.assertEqual(self.tn._negotiate(data), b"a\xffb")

    def test_subnegotiation_is_stripped(self):
        data = b"x" + bytes([IAC, SB, 24, 0, ord("A"), IAC, SE]) + b"y"
        self.assertEqual(self.tn._negotiate(data), b"xy")

    def test_incomplete_iac_sequence(self):
        self.assertEqual(self.tn._negotiate(b"ok" + bytes([IAC])), b"ok")


if __name__ == "__main__":
    unittest.main()
