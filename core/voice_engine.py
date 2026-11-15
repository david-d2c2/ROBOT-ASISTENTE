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
        self.zonos_model = _env("ZONOS_MODEL", "Zyphra/Zonos-v0.1-transformer")
        self.zonos_reference = _env("ZONOS_REFERENCE", "")  # wav con la voz a clonar (opcional)
        self.zonos_language = _env("ZONOS_LANGUAGE", "es")
        self.zonos_device = _env("ZONOS_DEVICE", "auto").lower()
        self.pitch = _env("TTS_PITCH", "+18Hz")
        self.rate = _env("TTS_RATE", "+8%")
        self.stt_provider = _env("STT_PROVIDER", "google").lower()
        self.stt_language = _env("STT_LANGUAGE", "es-ES")
        self.whisper_model = _env("WHISPER_MODEL", "base")
        self.whisper_device = _env("WHISPER_DEVICE", "auto")
        self.whisper_compute = _env("WHISPER_COMPUTE", "int8")
        self.mic_index = None
        raw_mic = os.getenv("MIC_INDEX", "").strip()
        if raw_mic.isdigit():
            self.mic_index = int(raw_mic)
        # Micrófono por nombre: los índices cambian al reiniciar o reconectar.
        self.mic_name = os.getenv("MIC_NAME", "").strip()
        self._whisper = None
        self._whisper_lock = threading.Lock()
        self._piper = None
        self._piper_lock = threading.Lock()
        self._zonos = None
        self._zonos_speaker_embedding = None
        self._zonos_lock = threading.Lock()

    def _resolved_mic_index(self) -> int | None:
        """Índice del micrófono elegido. El nombre manda (el índice guardado
        puede quedar obsoleto al cambiar dispositivos); si no se encuentra,
        predeterminado."""
        if self.mic_name:
            try:
                import pyaudio
                audio = pyaudio.PyAudio()
                try:
                    for index in range(audio.get_device_count()):
                        info = audio.get_device_info_by_index(index)
                        if info.get("maxInputChannels", 0) > 0 and str(info.get("name", "")).strip() == self.mic_name:
                            return index
                finally:
                    audio.terminate()
            except Exception:
                log.warning("No se pudo buscar el micrófono %r", self.mic_name, exc_info=True)
            log.warning("Micrófono %r no encontrado; se usa el predeterminado", self.mic_name)
        return self.mic_index

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

        suffix = ".wav" if self.tts_provider in ("piper", "zonos") else ".mp3"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name

        try:
            try:
                if self.tts_provider == "piper":
                    self._generate_piper(speech_text, tmp_path)
                elif self.tts_provider == "zonos":
                    self._generate_zonos(speech_text, tmp_path)
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
            with sr.Microphone(device_index=self._resolved_mic_index()) as source:
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
        """Devuelve el .onnx del modelo, descargándolo con el descargador oficial
        de Piper (URL y formato según la versión instalada) si falta."""
        path = self._piper_model_path()
        if path.exists():
            return path

        download_dir = path.parent
        download_dir.mkdir(parents=True, exist_ok=True)
        log.info("Descargando voz local %s (solo la primera vez)...", self.piper_voice)
        try:
            from piper.download_voices import download_voice
            download_voice(self.piper_voice, download_dir)
        except ImportError as exc:
            raise RuntimeError(
                "Para hablar sin conexión instala el paquete opcional: "
                "pip install -r requirements-tts.txt"
            ) from exc
        except Exception as exc:
            log.warning("Descarga de voz Piper fallida: %s", exc)
            raise RuntimeError(
                "No se pudo descargar la voz local. Prueba a mano: "
                f"python -m piper.download_voices {self.piper_voice} "
                f'--download-dir "{download_dir}"'
            ) from exc
        if not path.exists():
            raise RuntimeError("La descarga terminó pero no aparece el modelo esperado.")
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

    # ---- TTS local con Zonos (alta calidad, sin Internet ni Pinokio) ----

    def _ensure_zonos(self):
        """Carga el modelo Zonos una sola vez (GPU si la hay; la primera vez
        descarga los pesos desde Hugging Face)."""
        try:
            from zonos.model import Zonos
        except ImportError as exc:
            raise RuntimeError(
                "Para usar la voz Zonos instala el paquete opcional: "
                "pip install -r requirements-zonos.txt"
            ) from exc

        with self._zonos_lock:
            if self._zonos is None:
                device = self._zonos_resolve_device()
                log.info("Cargando Zonos (%s, %s)...", self.zonos_model, device)
                try:
                    self._zonos = Zonos.from_pretrained(self.zonos_model, device=device)
                except Exception as exc:
                    log.warning("Zonos no pudo cargar: %s", exc)
                    raise RuntimeError(
                        f"No se pudo cargar Zonos ({exc}). La primera vez descarga "
                        "varios GB desde Hugging Face; revisa conexión y VRAM."
                    ) from exc
        return self._zonos

    def _zonos_resolve_device(self) -> str:
        if self.zonos_device not in ("", "auto"):
            return self.zonos_device
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        log.info("Zonos sin GPU: funcionará en CPU (lento pero válido)")
        return "cpu"

    def _zonos_speaker(self):
        """Embedding de la voz a clonar desde un WAV de referencia (opcional)."""
        if not self.zonos_reference:
            return None
        with self._zonos_lock:
            if self._zonos_speaker_embedding is None:
                try:
                    import torch
                    import soundfile as sf
                    from zonos.conditioning import make_speaker
                    wav, rate = sf.read(self.zonos_reference, dtype="float32")
                    self._zonos_speaker_embedding = make_speaker(torch.from_numpy(wav), rate)
                except Exception as exc:
                    log.warning("Referencia de voz Zonos ilegible: %s", exc)
                    raise RuntimeError(
                        f"No pude leer el WAV de referencia «{self.zonos_reference}»."
                    ) from exc
        return self._zonos_speaker_embedding

    def _generate_zonos(self, text: str, output_file: str):
        model = self._ensure_zonos()
        try:
            import soundfile as sf
            import torch
            from zonos.conditioning import make_cond_dict
            conditioning = model.prepare_conditioning(
                make_cond_dict(
                    text=text,
                    speaker=self._zonos_speaker(),
                    language=self.zonos_language,
                )
            )
            codes = model.generate(conditioning)
            wavs = model.autoencoder.decode(codes).cpu()
            audio = wavs[0].numpy()
            rate = int(getattr(model.autoencoder, "sample_rate", 44_100) or 44_100)
            sf.write(output_file, audio, rate)
            del codes, wavs, audio  # liberar VRAM cuanto antes
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except RuntimeError:
            raise
        except Exception as exc:
            log.warning("Zonos falló al sintetizar: %s", exc)
            raise RuntimeError(
                "El motor Zonos falló al sintetizar. Si tu versión del paquete "
                "cambia la API, actualiza requirements-zonos.txt."
            ) from exc
