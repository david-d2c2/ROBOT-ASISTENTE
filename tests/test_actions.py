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

    def test_describe_pomodoro_and_remember(self):
        self.assertIn("pomodoro", actions.describe({"action": "pomodoro", "minutes": 25}).lower())
        self.assertIn("café", actions.describe({"action": "remember", "text": "tomo café"}))

    def test_pomodoro_schedules_notification(self):
        with patch("core.actions.QTimer") as qtimer:
            ok, message = actions.execute({"action": "pomodoro", "minutes": 25}, None)
        self.assertTrue(ok)
        qtimer.return_value.start.assert_called_once_with(1_500_000)
        actions._pomodoro_timer = None  # no filtrar el Mock a otros tests

    def test_second_pomodoro_replaces_the_previous(self):
        with patch("core.actions.QTimer") as qtimer:
            actions.execute({"action": "pomodoro", "minutes": 25}, None)
            ok, message = actions.execute({"action": "pomodoro", "minutes": 10}, None)
        self.assertTrue(ok)
        self.assertIn("Pomodoro", message)
        qtimer.return_value.stop.assert_called_once()
        actions._pomodoro_timer = None

    def test_pomodoro_announces_in_conversation_when_done(self):
        announced = []
        with patch("core.actions.QTimer") as qtimer:
            ok, _ = actions.execute(
                {"action": "pomodoro", "minutes": 1}, None, on_done=announced.append
            )
        self.assertTrue(ok)
        callback = qtimer.return_value.timeout.connect.call_args.args[0]
        callback()  # simula que el temporizador termina
        self.assertEqual(announced, ["🍅 Pomodoro terminado. Descansa 5 minutos."])
        actions._pomodoro_timer = None

    def test_reminder_announces_in_conversation_when_done(self):
        announced = []
        timer = Mock()
        with patch("core.actions.QTimer") as qtimer:
            qtimer.singleShot = timer
            actions.execute(
                {"action": "reminder", "minutes": 2, "message": "ropa"}, None,
                on_done=announced.append,
            )
        timer.call_args.args[1]()  # simula que el temporizador dispara
        self.assertEqual(announced, ["⏰ Recordatorio: ropa"])

    def test_remember_stores_the_fact(self):
        store = Mock()
        with patch("core.actions.MemoryStore", return_value=store):
            ok, message = actions.execute({"action": "remember", "text": "tomo café"}, None)
        self.assertTrue(ok)
        store.add.assert_called_once_with("tomo café")

    def test_rejects_empty_remember(self):
        ok, message = actions.execute({"action": "remember", "text": "   "}, None)
        self.assertFalse(ok)

    def test_describe_forget(self):
        self.assertIn("Olvidar", actions.describe({"action": "forget", "text": "mi cumpleaños"}))

    def test_forget_removes_matching_memories(self):
        store = Mock()
        store.remove.return_value = 2
        with patch("core.actions.MemoryStore", return_value=store):
            ok, message = actions.execute({"action": "forget", "text": "café"}, None)
        self.assertTrue(ok)
        store.remove.assert_called_once_with("café")
        self.assertIn("Olvidado", message)

    def test_forget_reports_when_nothing_matched(self):
        store = Mock()
        store.remove.return_value = 0
        with patch("core.actions.MemoryStore", return_value=store):
            ok, message = actions.execute({"action": "forget", "text": "perro"}, None)
        self.assertTrue(ok)
        self.assertIn("No tenía", message)

    def test_prompt_instructions_include_allowlist(self):
        with patch.object(app_settings, 'value', return_value="calc,notepad"):
            instructions = actions.build_prompt_instructions()
        self.assertIn("calc, notepad", instructions)
        self.assertIn("open_app", instructions)
        self.assertIn("pomodoro", instructions)
        self.assertIn("remember", instructions)


if __name__ == "__main__":
    unittest.main()
