import asyncio
import logging
import tempfile
import os
import re
import threading
import wave
from pathlib import Path

import edge_tts
import pygame
import requests
import speech_recognition as sr

log = logging.getLogger(__name__)

GOOGLE_STT_ENDPOINT = "https://www.google.com/speech-api/v2/recognize"
PIPER_VOICES_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/{locale_dir}/{locale}/{speaker}/{quality}/{name}.onnx"


def _env(name, default):
    value = os.getenv(name, "").strip()
    return value or default


def _piper_dir() -> Path:
    base = os.getenv("PIPER_MODEL_DIR", "").strip()
    if base:
        return Path(base)
    appdata = os.getenv("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "RobotAsistente" / "voices"


class VoiceEngine:
    def __init__(self):
        self._stopped = threading.Event()
        self.tts_provider = _env("TTS_PROVIDER", "edge").lower()
        self.voice = _env("TTS_VOICE", "es-ES-ElviraNeural")
        self.piper_voice = _env("PIPER_VOICE", "es_ES-davefx-medium")
        self.pitch = _env("TTS_PITCH", "+18Hz")
        self.rate = _env("TTS_RATE", "+8%")
        self.stt_provider = _env("STT_PROVIDER", "google").lower()
        self.stt_language = _env("STT_LANGUAGE", "es-ES")
        self.whisper_model = _env("WHISPER_MODEL", "base")
        self.whisper_device = _env("WHISPER_DEVICE", "auto")
        self.whisper_compute = _env("WHISPER_COMPUTE", "int8")
        self._whisper = None
        self._whisper_lock = threading.Lock()
        self._piper = None
        self._piper_lock = threading.Lock()

    def clean_text_for_speech(self, text: str) -> str:
        """Elimina asteriscos, símbolos Markdown y emojis antes de hablar."""
        # 1. Quitar los símbolos *, _, #, ~, ` para que nunca diga "asterisco" o "guion bajo"
        cleaned = re.sub(r'[\*\_\#\~\`\>]+', '', text)
        # 2. Limpiar espacios dobles
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    async def _generate_audio(self, text: str, output_file: str):
        communicate = edge_tts.Communicate(
            text, self.voice, pitch=self.pitch, rate=self.rate
        )
        await asyncio.wait_for(communicate.save(output_file), timeout=30)

    def stop(self):
        """Solicita el cierre; el hilo de voz libera sus propios recursos de audio."""
        self._stopped.set()

    def speak(self, text: str, should_stop=None):
        self._stopped.clear()  # un 'callar' anterior no debe silenciar la voz nueva
        def cancelled():
            return self._stopped.is_set() or (should_stop is not None and should_stop())

        speech_text = self.clean_text_for_speech(text)
        if not speech_text or cancelled():
            return

        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except Exception as exc:
            raise RuntimeError("No se pudo abrir la salida de audio. Revisa tus altavoces.") from exc

        suffix = ".wav" if self.tts_provider == "piper" else ".mp3"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name

        try:
            try:
                if self.tts_provider == "piper":
                    self._generate_piper(speech_text, tmp_path)
                else:
                    asyncio.run(self._generate_audio(speech_text, tmp_path))
            except RuntimeError:
                raise
            except Exception as exc:
                raise RuntimeError("No se pudo generar la voz. Revisa la conexión e inténtalo de nuevo.") from exc
            if cancelled():
                return
            try:
                pygame.mixer.music.load(tmp_path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    if cancelled():
                        break
                    pygame.time.Clock().tick(10)
            except Exception as exc:
                raise RuntimeError("No se pudo reproducir el audio. Revisa tus altavoces.") from exc
            finally:
                try:
                    try:
                        pygame.mixer.music.stop()
                    finally:
                        pygame.mixer.music.unload()
                except Exception as exc:
                    raise RuntimeError("No se pudo liberar la salida de audio.") from exc
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def listen(self) -> tuple[bool, str]:
        """Devuelve (Exito, Texto_o_Error)"""
        self._stopped.clear()  # cada escucha nueva resetea la petición de paro
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.8
        recognizer.operation_timeout = 15

        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio = recognizer.listen(source, timeout=6, phrase_time_limit=12)
        except sr.WaitTimeoutError:
            return False, "No detecté tu voz a tiempo. ¡Habla justo después de pulsar 🎤!"
        except OSError:
            return False, "Error de micrófono en Windows. Revisa sus permisos o conexión."
        except Exception:
            return False, "Error al procesar voz. Revisa la conexión e inténtalo de nuevo."

        if self._stopped.is_set():
            return False, "Escucha cancelada."

        try:
            if self.stt_provider == "whisper":
                text = self._transcribe_with_whisper(audio)
            else:
                text = recognizer.recognize_google(
                    audio, language=self.stt_language,
                    endpoint=GOOGLE_STT_ENDPOINT,
                )
            if not text or not text.strip():
                return False, "Te escuché, pero no entendí bien las palabras."
            return True, text
        except sr.UnknownValueError:
            return False, "Te escuché, pero no entendí bien las palabras."
        except ImportError:
            return False, "Para dictar sin conexión instala el paquete opcional: pip install -r requirements-whisper.txt"
        except Exception:
            return False, "Error al procesar voz. Revisa la conexión e inténtalo de nuevo."

    def _transcribe_with_whisper(self, audio) -> str:
        """Transcripción local con faster-whisper (modelo descargado en el primer uso)."""
        with self._whisper_lock:
            if self._whisper is None:
                from faster_whisper import WhisperModel
                self._whisper = WhisperModel(
                    self.whisper_model,
                    device=self.whisper_device,
                    compute_type=self.whisper_compute,
                )
        wav_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                wav_path = tmp.name
                tmp.write(audio.get_wav_data(convert_rate=16000, convert_width=2))
            language_code = self.stt_language.split("-")[0]
            segments, _info = self._whisper.transcribe(
                wav_path, language=language_code, beam_size=1
            )
            return "".join(segment.text for segment in segments).strip()
        finally:
            if wav_path and os.path.exists(wav_path):
                os.remove(wav_path)

    # ---- TTS local con Piper (sin Internet) ----

    def _piper_model_path(self) -> Path:
        return _piper_dir() / f"{self.piper_voice}.onnx"

    def _ensure_piper_model(self) -> Path:
        """Devuelve el .onnx del modelo, descargándolo de HuggingFace si falta."""
        path = self._piper_model_path()
        config = path.with_suffix(".onnx.json")
        if path.exists() and config.exists():
            return path

        parts = self.piper_voice.split("-")
        if len(parts) < 3:
            raise RuntimeError(
                "PIPER_VOICE debe tener el formato idioma_PAIS-locutor-calidad "
                "(por ejemplo es_ES-davefx-medium)."
            )
        locale, speaker, quality = parts[0], parts[1], parts[2]
        lang = locale.split("_")[0]
        url = PIPER_VOICES_URL.format(
            locale_dir=lang, locale=locale, speaker=speaker, quality=quality, name=self.piper_voice
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        log.info("Descargando voz local %s (solo la primera vez)...", self.piper_voice)
        try:
            for suffix in ("", ".json"):
                target = Path(str(path) + suffix)
                response = requests.get(url + suffix, stream=True, timeout=120)
                response.raise_for_status()
                with target.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1 << 20):
                        handle.write(chunk)
        except requests.RequestException as exc:
            log.warning("Descarga de voz Piper fallida: %s", exc)
            raise RuntimeError(
                "No se pudo descargar la voz local. Revisa la conexión o descárgala a mano: "
                f"{url} y {url}.json → {_piper_dir()}"
            ) from exc
        log.info("Voz local lista")
        return path

    def _generate_piper(self, text: str, output_file: str):
        try:
            from piper import PiperVoice  # se importa tarde: dependencia opcional
        except ImportError as exc:
            raise RuntimeError(
                "Para hablar sin conexión instala el paquete opcional: "
                "pip install -r requirements-tts.txt"
            ) from exc

        with self._piper_lock:
            if self._piper is None:
                model_path = self._ensure_piper_model()
                log.info("Cargando voz local Piper...")
                self._piper = PiperVoice.load(str(model_path))

        with wave.open(output_file, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            try:
                wav_file.setframerate(int(self._piper.config.sample_rate))
            except (AttributeError, TypeError, ValueError):
                wav_file.setframerate(22050)
            try:
                synth_wav = getattr(self._piper, "synthesize_wav", None)
                if synth_wav is not None:
                    synth_wav(text, wav_file)
                else:
                    self._piper.synthesize(text, wav_file=wav_file)
            except Exception as exc:
                raise RuntimeError("El motor de voz local falló al sintetizar.") from exc
