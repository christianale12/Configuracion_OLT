import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from network_terminal.backup.manager import (
    BackupManager,
    build_backup_filename,
    get_desktop_dir,
)


class FilenameTests(unittest.TestCase):
    def test_format(self):
        when = datetime(2026, 9, 8, 17, 45, 32)
        self.assertEqual(
            build_backup_filename("192.168.1.1", when),
            "192.168.1.1_2026-09-08_17-45-32.txt",
        )

    def test_sanitized(self):
        when = datetime(2026, 9, 8, 17, 45, 32)
        name = build_backup_filename("a/b c", when)
        self.assertTrue(name.startswith("a_b_c_"))
        self.assertRegex(name, r"^[A-Za-z0-9._-]+\.txt$")


class SaveTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.mgr = BackupManager(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_saves_file(self):
        path = self.mgr.save_config(
            "hello config", "10.0.0.1", datetime(2026, 1, 2, 3, 4, 5)
        )
        self.assertTrue(path.exists())
        self.assertEqual(path.read_text(encoding="utf-8"), "hello config")
        self.assertEqual(path.name, "10.0.0.1_2026-01-02_03-04-05.txt")

    def test_no_overwrite(self):
        when = datetime(2026, 1, 2, 3, 4, 5)
        p1 = self.mgr.save_config("a", "10.0.0.1", when)
        p2 = self.mgr.save_config("b", "10.0.0.1", when)
        self.assertNotEqual(p1, p2)
        self.assertTrue(p2.name.endswith("_1.txt"))
        self.assertEqual(p1.read_text(encoding="utf-8"), "a")

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            self.mgr.save_config("   ", "10.0.0.1")


class DesktopTests(unittest.TestCase):
    def test_returns_existing_dir(self):
        d = get_desktop_dir()
        self.assertIsInstance(d, Path)
        self.assertTrue(d.exists())


if __name__ == "__main__":
    unittest.main()
