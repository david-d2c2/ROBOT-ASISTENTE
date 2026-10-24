import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import memory_store


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / "memoria.db"
        patcher = patch.object(memory_store, "db_path", return_value=self.db)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = memory_store.MemoryStore()

    def tearDown(self):
        self.store.clear()

    def test_add_and_read_back(self):
        self.store.add("  le gusta el café  ")
        self.store.add("tiene un gato")
        self.assertEqual(self.store.all(), ["le gusta el café", "tiene un gato"])

    def test_all_limit_returns_most_recent_in_order(self):
        for number in range(5):
            self.store.add(f"hecho {number}")
        self.assertEqual(self.store.all(limit=2), ["hecho 3", "hecho 4"])

    def test_clear_removes_everything_and_the_file(self):
        self.store.add("secreto")
        self.store.clear()
        self.assertFalse(self.db.exists())
        self.assertEqual(self.store.all(), [])

    def test_store_is_reusable_after_clear(self):
        self.store.add("uno")
        self.store.clear()
        self.store.add("dos")
        self.assertEqual(self.store.all(), ["dos"])

    def test_clear_without_prior_use_still_removes_a_stale_file(self):
        self.db.write_bytes(b"base de datos vieja")
        self.store.clear()
        self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main()
