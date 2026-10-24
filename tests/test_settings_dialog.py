import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication

from core import app_settings, envfile
from ui.settings_dialog import SettingsDialog


class SettingsDialogSaveTests(unittest.TestCase):
    """Guardar no puede morir nunca: si falla, se pierden todos los cambios."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.env_file = Path(self.directory.name) / ".env"
        patcher = patch.object(envfile, "env_path", return_value=self.env_file)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _dialog(self):
        dialog = SettingsDialog()
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_accept_writes_env_and_settings(self):
        dialog = self._dialog()
        dialog.key_edit.setText("clave-de-prueba")
        dialog.accept()
        self.assertTrue(dialog.result())
        saved = envfile.read_env(self.env_file)
        self.assertEqual(saved["AI_PROVIDER"], "zai")
        self.assertEqual(saved["ZAI_API_KEY"], "clave-de-prueba")
        self.assertEqual(saved["TTS_PROVIDER"], "edge")
        self.assertTrue(app_settings.value("setup/done"))

    def test_accept_without_required_key_does_not_save(self):
        dialog = self._dialog()
        dialog.accept()
        self.assertFalse(dialog.result())
        self.assertFalse(self.env_file.exists())

    def test_accept_saves_with_local_provider_without_key(self):
        self.env_file.write_text("AI_PROVIDER=ollama\nLOCAL_LLM_MODEL=llama3.2\n", encoding="utf-8")
        dialog = self._dialog()
        dialog.accept()
        self.assertTrue(dialog.result())
        saved = envfile.read_env(self.env_file)
        self.assertEqual(saved["AI_PROVIDER"], "ollama")

    def test_switching_engine_swaps_default_voice(self):
        self.env_file.write_text(
            "TTS_PROVIDER=piper\nPIPER_VOICE=es_ES-davefx-medium\n", encoding="utf-8"
        )
        dialog = self._dialog()
        self.assertEqual(dialog.tts_edit.text(), "es_ES-davefx-medium")
        dialog.tts_provider_combo.setCurrentIndex(0)
        self.assertEqual(dialog.tts_edit.text(), "es-ES-ElviraNeural")

    def test_accept_never_leaks_an_edge_voice_into_piper(self):
        self.env_file.write_text("TTS_PROVIDER=edge\nTTS_VOICE=es-ES-ElviraNeural\n", encoding="utf-8")
        dialog = self._dialog()
        dialog.key_edit.setText("clave-de-prueba")
        dialog.tts_provider_combo.setCurrentIndex(1)  # Piper con la voz de Edge aún en el campo
        dialog.accept()
        saved = envfile.read_env(self.env_file)
        self.assertNotEqual(saved["PIPER_VOICE"], "es-ES-ElviraNeural")


if __name__ == "__main__":
    unittest.main()
