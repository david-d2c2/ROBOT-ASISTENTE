"""SFX: efectos generados por código y reproducidos a prueba de fallos."""
import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from core import sfx as sfx_mod
from core.sfx import SFX, generar_sfx, sfx_dir


class GeneracionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        # Los wav van a un directorio temporal, no a AppData.
        self.patcher = patch.object(sfx_mod, "sfx_dir",
                                    return_value=Path(self.directory.name))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_genera_wav_validos_para_cada_efecto(self):
        for nombre in ("bip", "error", "campanita", "motor"):
            with self.subTest(efecto=nombre):
                generar_sfx(sfx_dir() / f"{nombre}.wav", nombre)
        for wav in Path(self.directory.name).glob("*.wav"):
            with wave.open(str(wav), "rb") as handle:
                self.assertEqual(handle.getnchannels(), 1)
                self.assertGreater(handle.getnframes(), 0)

    def test_efecto_desconocido_rechazado(self):
        with self.assertRaises(ValueError):
            generar_sfx(Path(self.directory.name) / "x.wav", "disco")


class ReproduccionTests(unittest.TestCase):
    def setUp(self):
        self.mixer = patch("core.sfx.pygame.mixer").start()
        self.mixer.get_init.return_value = True
        self.addCleanup(patch.stopall)
        # Sin tocar AppData: los sonidos se generan pero no se leen de verdad.
        self.sound_patch = patch("core.sfx.pygame.mixer.Sound", return_value=MagicMock())
        self.sound = self.sound_patch.start()
        self.addCleanup(self.sound_patch.stop)

    def test_play_genera_y_reproduce(self):
        with patch.dict(os.environ, {"SFX_ENABLED": "1"}), \
             patch.object(sfx_mod, "sfx_dir", return_value=Path(tempfile.mkdtemp())):
            SFX().play("bip")
        self.sound.assert_called_once()
        self.sound.return_value.play.assert_called_once()

    def test_disabled_plays_nothing(self):
        with patch.dict(os.environ, {"SFX_ENABLED": "0"}):
            SFX().play("bip")
        self.sound.assert_not_called()

    def test_sound_failure_is_silent_and_not_retried(self):
        with patch.dict(os.environ, {"SFX_ENABLED": "1"}), \
             patch.object(sfx_mod, "sfx_dir", side_effect=OSError("sin disco")):
            motor = SFX()
            motor.play("bip")   # no revienta
            motor.play("bip")   # y no reintenta
        self.sound.assert_not_called()

    def test_motor_loops_once_and_stops(self):
        with patch.dict(os.environ, {"SFX_ENABLED": "1"}), \
             patch.object(sfx_mod, "sfx_dir", return_value=Path(tempfile.mkdtemp())):
            motor = SFX()
            motor.set_motor(True)
            canal = self.sound.return_value.play.return_value
            self.sound.return_value.play.assert_called_once_with(loops=-1)
            motor.set_motor(True)   # ya está sonando: no lo relanza
            self.sound.return_value.play.assert_called_once()
            motor.set_motor(False)
            canal.stop.assert_called_once()
            motor.set_motor(False)  # parar dos veces es inocuo
            canal.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
