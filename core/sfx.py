"""Efectos de sonido del robot, generados por código (sin assets binarios).

Los WAV se sintetizan la primera vez en AppData (senos con envolvente) y se
reproducen con pygame.mixer por canales, sin chocar con la voz (que usa
mixer.music). Cualquier fallo de audio se ignora: el SFX nunca tira la app.
"""
import logging
import math
import os
import struct
import wave
from pathlib import Path

import pygame

from PyQt6.QtCore import QStandardPaths

log = logging.getLogger(__name__)

SAMPLE_RATE = 22_050
VOLUMES = {"bip": 0.30, "error": 0.35, "campanita": 0.35, "motor": 0.10}


def sfx_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    directory = Path(base) / "RobotAsistente" / "sfx"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _write_wav(path: Path, muestras: list[float]):
    """Escribe muestras float (-1..1) como WAV mono de 16 bits."""
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for muestra in muestras:
            valor = max(-1.0, min(1.0, muestra))
            frames += struct.pack("<h", int(valor * 32_000))
        handle.writeframes(bytes(frames))


def _envolvente(i: int, total: int, borde: int) -> float:
    """Subida/bajada suaves para que no haya clics al empezar o terminar."""
    if i < borde:
        return i / borde
    if i > total - borde:
        return max(0.0, (total - i) / borde)
    return 1.0


def _tono(duracion: float, freq: float, borde_ms: float = 8.0) -> list[float]:
    total = int(SAMPLE_RATE * duracion)
    borde = int(SAMPLE_RATE * borde_ms / 1000)
    return [math.sin(2 * math.pi * freq * i / SAMPLE_RATE) * _envolvente(i, total, borde)
            for i in range(total)]


def generar_sfx(path: Path, nombre: str):
    """Sintetiza cada efecto: bip (clic), error (bajada), campanita (avisos)
    y motor (zumbido corto que se reproduce en bucle)."""
    if nombre == "bip":
        _write_wav(path, _tono(0.07, 880))
    elif nombre == "error":
        tono = _tono(0.22, 330)
        descendente = [muestra * (0.55 + 0.45 * (1 - i / len(tono)))
                       for i, muestra in enumerate(tono)]
        _write_wav(path, descendente)
    elif nombre == "campanita":
        base = _tono(0.32, 660)
        agudo = _tono(0.20, 990)
        mezcla = [a + 0.6 * b for a, b in zip(base, agudo + [0.0] * (len(base) - len(agudo)))]
        _write_wav(path, mezcla)
    elif nombre == "motor":
        total = int(SAMPLE_RATE * 0.3)
        borde = int(SAMPLE_RATE * 0.03)
        muestras = []
        for i in range(total):
            t = i / SAMPLE_RATE
            wobble = 1.0 + 0.04 * math.sin(2 * math.pi * 6.0 * t)
            muestras.append(
                0.6 * math.sin(2 * math.pi * 85.0 * t)
                + 0.25 * math.sin(2 * math.pi * 170.0 * t * wobble)
            )
        _write_wav(path, [m * _envolvente(i, total, borde) for i, m in enumerate(muestras)])
    else:
        raise ValueError(f"SFX desconocido: {nombre}")


class SFX:
    """Reproductor de efectos: discreto, opcional y a prueba de fallos."""

    def __init__(self):
        self._sounds: dict[str, "pygame.mixer.Sound"] = {}
        self._canal_motor = None

    # ---- Configuración ----

    def enabled(self) -> bool:
        return os.getenv("SFX_ENABLED", "1").strip().lower() not in ("0", "off", "false")

    def _sound(self, nombre: str):
        if nombre in self._sounds:
            return self._sounds[nombre]
        path = sfx_dir() / f"{nombre}.wav"
        try:
            if not path.exists():
                generar_sfx(path, nombre)
            sonido = pygame.mixer.Sound(str(path))
            sonido.set_volume(VOLUMES.get(nombre, 0.3))
            self._sounds[nombre] = sonido
            return sonido
        except Exception:
            log.info("SFX %s no disponible (sin audio)", nombre, exc_info=True)
            self._sounds[nombre] = None  # ni se reintenta: silencio digno
            return None

    # ---- Reproducción ----

    def play(self, nombre: str):
        """Un efecto puntual: bip, error, campanita."""
        if not self.enabled():
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            sonido = self._sound(nombre)
            if sonido is not None:
                sonido.play()
        except Exception:
            log.debug("No se pudo reproducir %s", nombre, exc_info=True)

    def set_motor(self, rodando: bool):
        """Zumbido de motor en bucle mientras rueda; idempotente."""
        try:
            if rodando:
                if self._canal_motor is not None and self._canal_motor.get_busy():
                    return
                if not self.enabled():
                    return
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                motor = self._sound("motor")
                if motor is not None:
                    self._canal_motor = motor.play(loops=-1)
            elif self._canal_motor is not None:
                self._canal_motor.stop()
                self._canal_motor = None
        except Exception:
            log.debug("Motor SFX no disponible", exc_info=True)
            self._canal_motor = None
