import os
import tempfile
import unittest
from pathlib import Path

from core import envfile


class EnvFileTests(unittest.TestCase):
    def setUp(self):
        self._saved_env = {
            key: os.environ.get(key)
            for key in ("AI_PROVIDER", "ZAI_API_KEY", "OPENAI_MODEL", "PERSONA")
        }

    def tearDown(self):
        for key, old in self._saved_env.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old

    def _temp_env(self, content: str) -> Path:
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".env", delete=False, encoding="utf-8"
        )
        handle.write(content)
        handle.close()
        self.addCleanup(os.remove, handle.name)
        return Path(handle.name)

    def test_read_parses_keys_and_ignores_comments(self):
        path = self._temp_env("# comentario\nAI_PROVIDER=zai\nZAI_API_KEY=abc\n\nVACIA=\n")
        self.assertEqual(
            envfile.read_env(path),
            {"AI_PROVIDER": "zai", "ZAI_API_KEY": "abc", "VACIA": ""},
        )

    def test_update_replaces_appends_and_preserves_comments(self):
        path = self._temp_env("# mis notas\nAI_PROVIDER=openai\nOPENAI_MODEL=gpt-4.1\n")
        envfile.update_env({"AI_PROVIDER": "zai", "ZAI_API_KEY": "clave"}, path=path)
        text = path.read_text(encoding="utf-8")
        self.assertIn("# mis notas", text)
        self.assertIn("AI_PROVIDER=zai", text)
        self.assertIn("ZAI_API_KEY=clave", text)
        self.assertIn("OPENAI_MODEL=gpt-4.1", text)
        self.assertEqual(os.environ.get("AI_PROVIDER"), "zai")

    def test_update_empty_value_removes_from_environment(self):
        path = self._temp_env("ZAI_API_KEY= vieja\n")
        os.environ["ZAI_API_KEY"] = "vieja"
        envfile.update_env({"ZAI_API_KEY": ""}, path=path)
        self.assertNotIn("ZAI_API_KEY", os.environ)
        self.assertIn("ZAI_API_KEY=", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
