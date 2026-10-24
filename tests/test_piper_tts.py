import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from core.voice_engine import VoiceEngine


class PiperTTSTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.model_dir = Path(self.directory.name) / "voices"
        self.model_dir.mkdir()
        self.mixer_patch = patch('core.voice_engine.pygame.mixer')
        self.mixer = self.mixer_patch.start()
        self.addCleanup(self.mixer_patch.stop)
        self.mixer.get_init.return_value = None
        self.mixer.music.get_busy.return_value = False
        self.original_temp = tempfile.NamedTemporaryFile
        temp_patch = patch(
            'core.voice_engine.tempfile.NamedTemporaryFile',
            side_effect=lambda **kw: self.original_temp(dir=self.directory.name, **kw),
        )
        temp_patch.start()
        self.addCleanup(temp_patch.stop)
        self.communicate_patch = patch('core.voice_engine.edge_tts.Communicate')
        self.communicate = self.communicate_patch.start()
        self.communicate.return_value.save = AsyncMock()
        self.addCleanup(self.communicate_patch.stop)
        self.fake_module = Mock()
        # El motor llama a PiperVoice.load(...), no al constructor.
        self.piper_voice = self.fake_module.PiperVoice.load.return_value
        self.piper_voice.config.sample_rate = 22050

    def _wav_files(self):
        return [name for name in os.listdir(self.directory.name) if name.endswith(".wav")]

    def _make_model(self):
        (self.model_dir / "es_ES-davefx-medium.onnx").write_bytes(b"modelo")
        (self.model_dir / "es_ES-davefx-medium.onnx.json").write_text("{}", encoding="utf-8")

    def test_piper_generates_local_audio_without_edge(self):
        self._make_model()
        env = {"TTS_PROVIDER": "piper", "PIPER_MODEL_DIR": str(self.model_dir)}
        with patch.dict(os.environ, env), patch.dict(sys.modules, {"piper": self.fake_module}):
            VoiceEngine().speak("Hola local")
        self.fake_module.PiperVoice.load.assert_called_once()
        self.piper_voice.synthesize_wav.assert_called_once()
        self.assertEqual(self.piper_voice.synthesize_wav.call_args.args[0], "Hola local")
        self.mixer.music.play.assert_called_once()
        self.assertEqual(self._wav_files(), [], "el wav temporal se limpia")

    def test_piper_downloads_model_on_first_use(self):
        fake_response = Mock()
        fake_response.iter_content.return_value = iter([b"datos"])
        env = {"TTS_PROVIDER": "piper", "PIPER_MODEL_DIR": str(self.model_dir)}
        with patch.dict(os.environ, env), patch.dict(sys.modules, {"piper": self.fake_module}):
            with patch('core.voice_engine.requests.get', return_value=fake_response) as get:
                VoiceEngine().speak("Hola")
        self.assertEqual(get.call_count, 2)  # .onnx + .json
        self.assertIn("davefx/medium", get.call_args_list[0].args[0])
        self.assertTrue((self.model_dir / "es_ES-davefx-medium.onnx").exists())

    def test_piper_missing_package_is_friendly(self):
        self._make_model()
        env = {"TTS_PROVIDER": "piper", "PIPER_MODEL_DIR": str(self.model_dir)}
        with patch.dict(os.environ, env), patch.dict(sys.modules, {"piper": None}):
            with self.assertRaisesRegex(RuntimeError, "requirements-tts"):
                VoiceEngine().speak("Hola")
        self.mixer.music.play.assert_not_called()

    def test_edge_remains_the_default_provider(self):
        self.mixer.music.load.return_value = None
        VoiceEngine().speak("Hola")
        self.fake_module.PiperVoice.load.assert_not_called()
        self.mixer.music.play.assert_called_once()


if __name__ == "__main__":
    unittest.main()
