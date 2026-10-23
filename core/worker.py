"""Worker de IA: transcribe, consulta con streaming y sintetiza. QThread."""
import logging

from PyQt6.QtCore import QThread, pyqtSignal

from core.ai_engine import AIEngine, AIError
from core.voice_engine import VoiceEngine

log = logging.getLogger(__name__)


class AIWorker(QThread):
    status_update = pyqtSignal(str)
    partial_ready = pyqtSignal(str)
    answer_ready = pyqtSignal(str)
    state_changed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, ai: AIEngine, voice: VoiceEngine, prompt: str,
                 use_mic: bool = False, speech_enabled: bool = True, history=None):
        super().__init__()
        self.ai = ai
        self.voice = voice
        self.prompt = prompt
        self.use_mic = use_mic
        self.speech_enabled = speech_enabled
        self.history = history or []
        self.final_query = prompt

    def run(self):
        log.info("Worker iniciado (mic=%s, historia=%d)", self.use_mic, len(self.history))
        try:
            query = self.prompt
            if self.isInterruptionRequested():
                return
            if self.use_mic:
                ok, result = self.voice.listen()
                if self.isInterruptionRequested():
                    return
                if not ok:
                    self.failed.emit(result)
                    return
                query = result
                self.final_query = query
                self.state_changed.emit("THINKING")
                self.status_update.emit(f"Tú: «{query}»\nPensando...")

            answer = ""
            ask_stream = getattr(self.ai, "ask_stream", None)
            if ask_stream is not None:
                for chunk in ask_stream(query, list(self.history)):
                    if self.isInterruptionRequested():
                        return
                    answer += chunk
                    if answer.strip():
                        self.partial_ready.emit(answer)
            else:
                answer = self.ai.ask(query)
            if self.isInterruptionRequested():
                return
            answer = answer.strip()
            if not answer:
                self.failed.emit("El proveedor de IA devolvió una respuesta vacía.")
                return
            log.debug("Respuesta completa (%d caracteres)", len(answer))
            self.answer_ready.emit(answer)
        except AIError as error:
            log.warning("Error de IA: %s", error)
            self.failed.emit(str(error))
            return
        except Exception:
            log.exception("Fallo inesperado en el worker")
            self.failed.emit("No pude completar la consulta. Comprueba la conexión y la configuración.")
            return

        if self.speech_enabled and not self.isInterruptionRequested():
            self.state_changed.emit("SPEAKING")
            try:
                self.voice.speak(answer, should_stop=lambda: self.isInterruptionRequested() or not self.speech_enabled)
            except Exception:
                log.warning("Fallo de reproducción de voz", exc_info=True)
                self.failed.emit("La respuesta está escrita, pero no pude reproducir la voz.")
