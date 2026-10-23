import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core import actions, app_settings


class ActionExtractionTests(unittest.TestCase):
    def test_extracts_json_action_from_text(self):
        text = 'Vale, voy: {"action": "open_app", "app": "calc"}'
        self.assertEqual(
            actions.extract_action(text),
            {"action": "open_app", "app": "calc"},
        )

    def test_ignores_plain_text_and_unknown_actions(self):
        self.assertIsNone(actions.extract_action("Respuesta normal sin JSON."))
        self.assertIsNone(actions.extract_action('{"action": "format_c"}'))
        self.assertIsNone(actions.extract_action('{"roto": [}'))

    def test_describe_each_action(self):
        self.assertIn("calc", actions.describe({"action": "open_app", "app": "calc"}))
        self.assertIn("web", actions.describe({"action": "open_url", "url": "https://x"}))


class ActionExecutionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.notes = Path(self.directory.name) / "notas.txt"

    def test_open_app_denies_apps_outside_allowlist(self):
        with patch.object(app_settings, 'value', return_value="calc,notepad"):
            ok, message = actions.execute({"action": "open_app", "app": "cmd"}, None)
        self.assertFalse(ok)
        self.assertIn("no está", message)

    def test_open_url_rejects_non_http_schemes(self):
        ok, message = actions.execute({"action": "open_url", "url": "file:///C:/"}, None)
        self.assertFalse(ok)
        with patch("core.actions.os.startfile") as startfile:
            ok, message = actions.execute({"action": "open_url", "url": "https://example.com"}, None)
        self.assertTrue(ok)
        startfile.assert_called_once_with("https://example.com")

    def test_note_writes_timestamped_line(self):
        with patch.object(actions, "notes_path", return_value=self.notes):
            ok, message = actions.execute({"action": "note", "text": "comprar café"}, None)
        self.assertTrue(ok)
        self.assertIn("comprar café", self.notes.read_text(encoding="utf-8"))

    def test_reminder_schedules_notification(self):
        timer = Mock()
        with patch("core.actions.QTimer") as qtimer:
            qtimer.singleShot = timer
            ok, message = actions.execute(
                {"action": "reminder", "minutes": 2, "message": "pausa"}, None
            )
        self.assertTrue(ok)
        timer.assert_called_once()
        self.assertEqual(timer.call_args.args[0], 120_000)

    def test_prompt_instructions_include_allowlist(self):
        with patch.object(app_settings, 'value', return_value="calc,notepad"):
            instructions = actions.build_prompt_instructions()
        self.assertIn("calc, notepad", instructions)
        self.assertIn("open_app", instructions)


if __name__ == "__main__":
    unittest.main()
