import tempfile
import threading
import unittest
from pathlib import Path

from network_terminal.batch.runner import (
    BulkConfig,
    download_configs,
    parse_targets,
)
from network_terminal.core.errors import TerminalError
from network_terminal.tests._fakes import FakeConnection, ScriptedConnection


class ParseTargetsTests(unittest.TestCase):
    def test_mixed_separators_and_dedup(self):
        raw = "10.0.0.1, 10.0.0.2\n10.0.0.3 10.0.0.1\n# comentario\n\n;10.0.0.2"
        valid, invalid = parse_targets(raw)
        self.assertEqual(valid, ["10.0.0.1", "10.0.0.2", "10.0.0.3"])
        self.assertEqual(invalid, [])

    def test_invalid_hosts_separated(self):
        valid, invalid = parse_targets("router1.lab\nbad_host!name")
        self.assertEqual(valid, ["router1.lab"])
        self.assertEqual(invalid, ["bad_host!name"])

    def test_empty(self):
        self.assertEqual(parse_targets("  \n # solo comentario\n"), ([], []))


class DownloadConfigsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dest = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _ok_factory(self, host, cfg):
        return FakeConnection(script=["prompt> ", f"config de {host}\nlinea-2\n"])

    def test_all_hosts_saved_in_order(self):
        cfg = BulkConfig(read_quiet=0.15, read_timeout=2.0, max_workers=3)
        hosts = ["10.0.0.1", "10.0.0.2", "10.0.0.3"]
        seen = []
        results = download_configs(
            hosts,
            cfg,
            backup_dir=self.dest,
            connection_factory=self._ok_factory,
            on_result=lambda r: seen.append(r.host),
        )
        self.assertEqual([r.host for r in results], hosts)
        self.assertTrue(all(r.ok for r in results))
        self.assertEqual(len(list(self.dest.glob("*.txt"))), 3)
        self.assertEqual(sorted(seen), hosts)

    def test_one_failure_does_not_stop_others(self):
        def factory(host, cfg):
            if host == "10.0.0.2":
                raise TerminalError("boom", user_message="No se pudo conectar.")
            return self._ok_factory(host, cfg)

        cfg = BulkConfig(read_quiet=0.15, read_timeout=2.0)
        results = {
            r.host: r
            for r in download_configs(
                ["10.0.0.1", "10.0.0.2", "10.0.0.3"],
                cfg,
                backup_dir=self.dest,
                connection_factory=factory,
            )
        }
        self.assertTrue(results["10.0.0.1"].ok)
        self.assertFalse(results["10.0.0.2"].ok)
        self.assertEqual(results["10.0.0.2"].error, "No se pudo conectar.")
        self.assertTrue(results["10.0.0.3"].ok)
        self.assertEqual(len(list(self.dest.glob("*.txt"))), 2)

    def test_empty_config_is_error_and_not_saved(self):
        cfg = BulkConfig(read_quiet=0.15, read_timeout=2.0)
        results = download_configs(
            ["10.0.0.9"],
            cfg,
            backup_dir=self.dest,
            connection_factory=lambda h, c: FakeConnection(script=["   \n"]),
        )
        self.assertFalse(results[0].ok)
        self.assertEqual(list(self.dest.glob("*.txt")), [])

    def test_output_yaml_only(self):
        responses = {
            "/interface print detail without-paging": ' 0 R name="ether1" mtu=1500\n',
            "/ip address print detail without-paging": (
                " 0 address=1.1.1.1/24 interface=ether1\n"
            ),
        }
        cfg = BulkConfig(
            output="yaml",
            include_raw=False,
            read_quiet=0.1,
            read_timeout=1.0,
            max_workers=2,
        )
        results = download_configs(
            ["10.0.0.1", "10.0.0.2"],
            cfg,
            backup_dir=self.dest,
            connection_factory=lambda h, c: ScriptedConnection(responses, default="#\r\n"),
        )
        self.assertTrue(all(r.ok for r in results))
        self.assertEqual(len(list(self.dest.glob("*.yaml"))), 2)
        self.assertEqual(list(self.dest.glob("*.txt")), [])

    def test_output_both(self):
        responses = {
            "/export": "config text de ejemplo\n",
            "/interface print detail without-paging": ' 0 name="e1" mtu=1500\n',
        }
        cfg = BulkConfig(
            output="both", include_raw=False, read_quiet=0.1, read_timeout=1.0
        )
        results = download_configs(
            ["10.0.0.1"],
            cfg,
            backup_dir=self.dest,
            connection_factory=lambda h, c: ScriptedConnection(responses, default="#\r\n"),
        )
        self.assertTrue(results[0].ok)
        self.assertEqual(len(results[0].paths), 2)
        self.assertEqual(len(list(self.dest.glob("*.txt"))), 1)
        self.assertEqual(len(list(self.dest.glob("*.yaml"))), 1)

    def test_cancel_event_skips_everything(self):
        ev = threading.Event()
        ev.set()
        cfg = BulkConfig(read_quiet=0.1, read_timeout=1.0)
        results = download_configs(
            ["10.0.0.1", "10.0.0.2"],
            cfg,
            backup_dir=self.dest,
            connection_factory=self._ok_factory,
            cancel_event=ev,
        )
        self.assertTrue(all(not r.ok for r in results))
        self.assertEqual([r.error for r in results], ["Cancelado", "Cancelado"])
        self.assertEqual(list(self.dest.glob("*.txt")), [])


if __name__ == "__main__":
    unittest.main()
