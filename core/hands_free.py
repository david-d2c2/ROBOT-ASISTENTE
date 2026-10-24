"""Modo manos libres: escucha continua con palabra de activación local.

El bucle escucha frases cortas; si empiezan con una palabra de activación
('robot', 'oye', 'bmo'...), extrae el comando y lo manda al robot. Con
STT_PROVIDER=whisper funciona totalmente sin conexión.
"""
import logging
import re
import threading

from PyQt6.QtCore import QThread, pyqtSignal

from core import app_settings

log = logging.getLogger(__name__)

DEFAULT_WAKE_WORDS = "robot,oye,bmo"


def wake_words() -> tuple[str, ...]:
    raw = app_settings.env("WAKE_WORDS", DEFAULT_WAKE_WORDS)
    words = tuple(w.strip().lower() for w in raw.split(",") if w.strip())
    return words or ("robot",)


def extract_command(text: str, words=None) -> str | None:
    """Devuelve el comando tras la(s) palabra(s) de activación.

    - None: el texto no despierta al robot.
    - "": despertó sin comando (solo dijo la palabra).
    - "abre la calculadora": despertó y pidió esto.
    Acepta hasta tres palabras de activación encadenadas ('oye robot ...').
    """
    words = set(words or wake_words())
    cleaned = re.sub(r"[^\w\sáéíóúüñ]", " ", (text or "").lower()).strip()
    consumed = False
    for _ in range(3):
        head, _, tail = cleaned.partition(" ")
        if head in words:
            consumed = True
            cleaned = tail.strip()
        else:
            break
    if not consumed:
        return None
    return cleaned


class HandsFreeLoop(QThread):
    """Bucle de escucha en segundo plano mientras el modo está activo."""

    command_ready = pyqtSignal(str)

    def __init__(self, voice):
        super().__init__()
        self.voice = voice
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()
        # Corta una escucha en curso para que el bucle termine rápido.
        self.voice.stop()

    def run(self):
        log.info("Modo manos libres activado (palabras: %s)", ", ".join(wake_words()))
        while not self._stop.is_set():
            try:
                ok, text = self.voice.listen()
            except Exception:
                log.exception("Fallo de escucha en manos libres")
                self._stop.wait(1.0)
                continue
            if self._stop.is_set():
                break
            if not ok:
                continue
            command = extract_command(text)
            if command is None:
                continue
            log.info("Manos libres: despertó con comando %r", command)
            self.command_ready.emit(command)
            self._stop.wait(1.0)  # evita reactivarse con el eco de la respuesta
        log.info("Modo manos libres desactivado")
