"""Filesystem migration tests using real files in isolated temporary directories."""
import importlib
from pathlib import Path
import json
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1] / "custom_components/tauron_virtual_meter"
package = types.ModuleType("storage_test_package")
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
storage = importlib.import_module("storage_test_package.storage")


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / ".storage"
        self.root.mkdir()
        self.target = self.root / "tauron_virtual_meter"
        self.prefix = "tauron_virtual_meter.entry."

    def test_storage_key_uses_requested_subdirectory(self):
        self.assertEqual(storage.storage_key("entry", "index"),
                         "tauron_virtual_meter/tauron_virtual_meter.entry.index")

    def test_fresh_install_creates_directory(self):
        self.assertEqual(storage.migrate_storage(self.root, "entry")["moved"], 0)
        self.assertTrue(self.target.is_dir())

    def test_moves_index_and_raw_files_without_changing_contents(self):
        content = json.dumps({"version": 1, "key": self.prefix + "index", "data": {
            "cursor": "2025-01-13", "history_retry_after": "2026-11-26T13:47:22+00:00",
            "history_day_progress": {"day": "2025-01-13", "completed": ["profile.consum"]},
        }}).encode()
        for suffix in ("index", "2025-01-13.consum", "2025-01-13.readings.oze", "latest_month.consum", "meters"):
            (self.root / (self.prefix + suffix)).write_bytes(content)
        counts = storage.migrate_storage(self.root, "entry")
        self.assertEqual(counts["moved"], 5)
        for path in self.target.iterdir():
            self.assertEqual(path.read_bytes(), content)
        self.assertEqual(list(self.root.glob(self.prefix + "*")), [])

    def test_leaves_other_integrations_entries_directories_and_symlinks_alone(self):
        for name in ("core.config_entries", "tauron_virtual_meter.other.index", "tauron_virtual_meter.entry_other.index"):
            (self.root / name).write_text("keep")
        directory = self.root / (self.prefix + "directory")
        directory.mkdir()
        link = self.root / (self.prefix + "link")
        link.symlink_to(self.root / "core.config_entries")
        self.assertEqual(storage.migrate_storage(self.root, "entry")["moved"], 0)
        self.assertTrue(link.is_symlink())
        self.assertTrue(directory.is_dir())
        self.assertEqual((self.root / "core.config_entries").read_text(), "keep")

    def test_existing_destination_wins_and_legacy_data_is_preserved(self):
        self.target.mkdir()
        name = self.prefix + "index"
        (self.root / name).write_text("older data")
        (self.target / name).write_text("newer data")
        counts = storage.migrate_storage(self.root, "entry")
        self.assertEqual(counts["conflicts"], 1)
        self.assertEqual((self.target / name).read_text(), "newer data")
        self.assertEqual((self.target / "legacy" / name).read_text(), "older data")
        self.assertFalse((self.root / name).exists())

    def test_identical_duplicates_and_repeated_migration_are_safe(self):
        self.target.mkdir()
        name = self.prefix + "index"
        (self.root / name).write_text("same")
        (self.target / name).write_text("same")
        self.assertEqual(storage.migrate_storage(self.root, "entry")["duplicates"], 1)
        self.assertFalse((self.root / name).exists())
        self.assertEqual(storage.migrate_storage(self.root, "entry"), {"moved": 0, "duplicates": 0, "conflicts": 0})
        self.assertEqual((self.target / name).read_text(), "same")

    def test_interrupted_migration_resumes_from_remaining_files(self):
        for suffix in ("2025-01-13.consum", "index"):
            (self.root / (self.prefix + suffix)).write_text(suffix)
        rename = Path.rename
        calls = 0

        def fail_second(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated interruption")
            return rename(source, destination)

        with patch.object(Path, "rename", fail_second), self.assertRaises(OSError):
            storage.migrate_storage(self.root, "entry")
        self.assertTrue((self.root / (self.prefix + "index")).exists())
        self.assertEqual(storage.migrate_storage(self.root, "entry")["moved"], 1)
        self.assertEqual((self.target / (self.prefix + "index")).read_text(), "index")
        self.assertEqual((self.target / (self.prefix + "2025-01-13.consum")).read_text(), "2025-01-13.consum")

    def test_conflicting_legacy_backup_is_not_overwritten(self):
        self.target.mkdir()
        name = self.prefix + "index"
        (self.target / name).write_text("active")
        for text in ("legacy one", "legacy two"):
            (self.root / name).write_text(text)
            storage.migrate_storage(self.root, "entry")
        self.assertEqual((self.target / "legacy" / name).read_text(), "legacy one")
        self.assertEqual((self.target / "legacy" / (name + ".1")).read_text(), "legacy two")


if __name__ == "__main__":
    unittest.main()
