import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import app_settings
from core.chat_store import ChatStore


class ChatStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / "chat.db"

    def test_disabled_by_default_never_touches_disk(self):
        with patch('core.chat_store.db_path', return_value=self.db), \
                patch.object(app_settings, 'value', return_value=False):
            store = ChatStore()
            store.append("user", "hola")
            self.assertEqual(store.load_recent(), [])
            self.assertFalse(self.db.exists())

    def test_persists_loads_and_clears(self):
        store = ChatStore()
        self.addCleanup(store.close)
        with patch('core.chat_store.db_path', return_value=self.db), \
                patch.object(app_settings, 'value', return_value=True):
            store.append("user", "hola")
            store.append("assistant", "bip")
            self.assertEqual(store.load_recent(), [("user", "hola"), ("assistant", "bip")])
            self.assertEqual(store.load_recent(limit=1), [("assistant", "bip")])
            store.clear()
            self.assertEqual(store.load_recent(), [])


if __name__ == "__main__":
    unittest.main()
