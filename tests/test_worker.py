import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication

from core.worker import AIWorker


class FakeVoice:
    def __init__(self, transcription):
        self.transcription = transcription
        self.spoken = []

    def listen(self):
        return True, self.transcription

    def speak(self, text, should_stop=None):
        self.spoken.append(text)


class FakeAI:
    def ask_stream(self, *args, **kwargs):
        raise AssertionError("Con una habilidad local no debía llamarse a la IA")


class VoiceSkillTests(unittest.TestCase):
    """Las habilidades locales también responden a lo dictado por voz."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_voice_prompt_answers_with_local_skill_without_ai(self):
        voice = FakeVoice("modo demo")
        skill = {"name": "demo", "triggers": ["demo"], "response": "Habilidad activada.", "say": False}
        answers, states = [], []
        with patch("core.worker.local_skills.match_skill", return_value=skill):
            worker = AIWorker(FakeAI(), voice, "", use_mic=True, speech_enabled=False)
            worker.answer_ready.connect(answers.append)
            worker.state_changed.connect(states.append)
            worker.run()  # síncrono, sin hilo real
        self.assertEqual(answers, ["Habilidad activada."])
        self.assertEqual(worker.final_query, "modo demo")
        self.assertNotIn("SPEAKING", states)
        self.assertEqual(voice.spoken, [])

    def test_voice_skill_with_say_speaks_the_response(self):
        voice = FakeVoice("modo demo")
        skill = {"name": "demo", "triggers": ["demo"], "response": "Habilidad activada.", "say": True}
        states = []
        with patch("core.worker.local_skills.match_skill", return_value=skill):
            worker = AIWorker(FakeAI(), voice, "", use_mic=True, speech_enabled=True)
            worker.state_changed.connect(states.append)
            worker.run()
        self.assertEqual(voice.spoken, ["Habilidad activada."])
        self.assertIn("SPEAKING", states)


if __name__ == "__main__":
    unittest.main()
