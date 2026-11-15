import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from core.voice_engine import VoiceEngine


def _fake_zonos_modules(model_mock=None):
    """Módulos zonos/torch/soundfile falsos para probar el motor sin pesos."""
    model_mock = model_mock or MagicMock()
    zonos = Mock()
    zonos.model.Zonos.from_pretrained.return_value = model_mock
    soundfile = Mock()
    soundfile.read.return_value = ([0.0, 0.1], 44_100)
    torch = Mock()
    torch.cuda.is_available.return_value = False
    return {"zonos.model": zonos.model, "zonos.conditioning": zonos.conditioning,
            "soundfile": soundfile, "torch": torch}, model_mock, zonos.conditioning


class ZonosTTSTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
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
        communicate_patch = patch('core.voice_engine.edge_tts.Communicate')
        communicate = communicate_patch.start()
        communicate.save = AsyncMock()
        self.addCleanup(communicate_patch.stop)

    def test_zonos_generates_audio_and_plays_it(self):
        modulos, modelo, condicionamiento = _fake_zonos_modules(model_mock=MagicMock())
        modelo.autoencoder.sample_rate = 44_100
        modelo.autoencoder.decode.return_value.cpu.return_value.__getitem__.return_value.numpy.return_value = [0.0]
        env = {"TTS_PROVIDER": "zonos", "ZONOS_DEVICE": "cpu"}
        with patch.dict(os.environ, env), patch.dict(sys.modules, modulos):
            VoiceEngine().speak("Hola desde Zonos")
        zonos_from_pretrained = modulos["zonos.model"].Zonos.from_pretrained
        zonos_from_pretrained.assert_called_once()
        self.assertEqual(zonos_from_pretrained.call_args.kwargs.get("device"), "cpu")
        condicionamiento.make_cond_dict.assert_called_once()
        self.assertEqual(
            condicionamiento.make_cond_dict.call_args.kwargs.get("text"), "Hola desde Zonos"
        )
        modelo.generate.assert_called_once()
        modulos["soundfile"].write.assert_called_once()
        self.mixer.music.play.assert_called_once()

    def test_zonos_model_loads_once_across_calls(self):
        modulos, modelo, _ = _fake_zonos_modules(model_mock=MagicMock())
        env = {"TTS_PROVIDER": "zonos", "ZONOS_DEVICE": "cpu"}
        with patch.dict(os.environ, env), patch.dict(sys.modules, modulos):
            engine = VoiceEngine()
            engine.speak("primera")
            engine.speak("segunda")
        modulos["zonos.model"].Zonos.from_pretrained.assert_called_once()

    def test_zonos_missing_package_is_friendly(self):
        env = {"TTS_PROVIDER": "zonos"}
        with patch.dict(os.environ, env), patch.dict(sys.modules, {"zonos.model": None}):
            with self.assertRaisesRegex(RuntimeError, "requirements-zonos"):
                VoiceEngine().speak("Hola")
        self.mixer.music.play.assert_not_called()

    def test_reference_wav_creates_speaker_and_none_if_unset(self):
        modulos, _, condicionamiento = _fake_zonos_modules()
        modelo = modulos["zonos.model"].Zonos.from_pretrained.return_value
        modelo.generate.return_value = object()
        env = {"TTS_PROVIDER": "zonos", "ZONOS_DEVICE": "cpu"}
        with patch.dict(os.environ, env), patch.dict(sys.modules, modulos):
            engine = VoiceEngine()
            engine.speak("sin clonar")
        condicionamiento.make_speaker.assert_not_called()

        referencia = Path(self.directory.name) / "mi_voz.wav"
        referencia.write_bytes(b"RIFF....")
        env2 = {**env, "ZONOS_REFERENCE": str(referencia)}
        with patch.dict(os.environ, env2), patch.dict(sys.modules, modulos):
            VoiceEngine().speak("clonando")
        condicionamiento.make_speaker.assert_called_once()


if __name__ == "__main__":
    unittest.main()
