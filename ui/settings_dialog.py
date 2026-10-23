"""Panel de ajustes: proveedor, claves, voz y comportamiento — sin editar .env a mano."""
import logging

from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSpinBox, QVBoxLayout,
)

from core import envfile
from core.ai_engine import PERSONAS
from core.app_settings import set_value, value

log = logging.getLogger(__name__)

PROVIDERS = [
    ("Z.AI (GLM)", "zai", "ZAI_API_KEY", "glm-4.6", True),
    ("OpenAI", "openai", "OPENAI_API_KEY", "gpt-4.1", False),
    ("Gemini", "gemini", "GEMINI_API_KEY", "", False),
    ("Ollama (local)", "ollama", "", "llama3.2", False),
    ("LM Studio (local)", "lmstudio", "", "", False),
    ("llama.cpp (local)", "llamacpp", "", "", True),
]

PERSONA_LABELS = [("Humor ácido 😏", "acido"), ("Normal 🙂", "normal"), ("Técnico 🛠️", "tecnico")]

DIALOG_QSS = (
    "QDialog, QLabel, QCheckBox, QSpinBox { background: #0B1220; color: #CFF9FF; }"
    "QLineEdit, QComboBox { background: #101B2E; color: #E4FDFF;"
    " border: 1px solid rgba(0,240,255,90); border-radius: 6px; padding: 4px 6px; }"
    "QPushButton { background: #123243; color: #8FF7FF;"
    " border: 1px solid rgba(0,240,255,110); border-radius: 6px; padding: 5px 12px; }"
    "QPushButton:hover { border: 1px solid #00F0FF; }"
)


class ProbeWorker(QThread):
    done = pyqtSignal(bool, str)

    def __init__(self, provider_values: dict):
        super().__init__()
        self.values = provider_values

    def run(self):
        import os
        from core.ai_engine import AIEngine
        previous = {key: os.environ.get(key) for key in self.values}
        try:
            os.environ.update(self.values)
            answer = AIEngine().ask("Responde solo: OK")
            self.done.emit(bool(answer.strip()), answer.strip()[:80] or "Respuesta vacía")
        except Exception as exc:
            log.info("Prueba de conexión fallida: %s", exc)
            self.done.emit(False, str(exc))
        finally:
            for key, old in previous.items():
                if old is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old


class SettingsDialog(QDialog):
    def __init__(self, parent=None, wizard: bool = False):
        super().__init__(parent)
        self.wizard = wizard
        self.setWindowTitle("Ajustes — Robot Asistente")
        self.setStyleSheet(DIALOG_QSS)
        self.setMinimumWidth(430)
        self.probe_worker = None

        current = envfile.read_env()
        layout = QVBoxLayout(self)
        if wizard:
            welcome = QLabel(
                "¡Hola! Soy BMO-Bot. Para pensar necesito que me conectes a un cerebro:\n"
                "elige un proveedor de IA y pega tu clave. Puedes cambiarlo luego aquí mismo."
            )
            welcome.setWordWrap(True)
            layout.addWidget(welcome)

        form = QFormLayout()
        self.provider_combo = QComboBox()
        for label, _code, _key, _model, _base in PROVIDERS:
            self.provider_combo.addItem(label)
        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        form.addRow("Proveedor", self.provider_combo)

        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("Pega tu clave de API")
        form.addRow("Clave API", self.key_edit)

        self.model_edit = QLineEdit()
        form.addRow("Modelo", self.model_edit)

        self.base_url_edit = QLineEdit()
        form.addRow("URL base", self.base_url_edit)

        self.persona_combo = QComboBox()
        for label, _code in PERSONA_LABELS:
            self.persona_combo.addItem(label)
        form.addRow("Personalidad", self.persona_combo)

        self.history_spin = QSpinBox()
        self.history_spin.setRange(0, 30)
        self.history_spin.setToolTip("Turnos (pregunta+respuesta) que el robot recuerda")
        form.addRow("Memoria (turnos)", self.history_spin)

        self.tts_edit = QLineEdit()
        form.addRow("Voz TTS", self.tts_edit)

        self.stt_combo = QComboBox()
        self.stt_combo.addItem("Google (Internet)")
        self.stt_combo.addItem("Whisper local (sin conexión)")
        form.addRow("Dictado", self.stt_combo)

        self.actions_check = QCheckBox("Permitir acciones de escritorio (con confirmación)")
        form.addRow("", self.actions_check)

        self.persist_check = QCheckBox("Recordar la conversación entre sesiones")
        form.addRow("", self.persist_check)

        layout.addLayout(form)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        self.probe_btn = QPushButton("Probar conexión")
        self.probe_btn.clicked.connect(self._probe)
        buttons.addWidget(self.probe_btn)
        buttons.addStretch(1)
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Guardar")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.accept)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

        self._load(current)
        self._provider_changed()

    # ---- Carga y correspondencia proveedor ↔ campos ----

    def _load(self, env: dict):
        provider = env.get("AI_PROVIDER", "zai").lower()
        for index, (_label, code, key, model, _base) in enumerate(PROVIDERS):
            if code == provider:
                self.provider_combo.setCurrentIndex(index)
                self.key_edit.setText(env.get(key, "") if key else "")
                self.model_edit.setText(env.get(_model_key(code), model or ""))
                break
        self.base_url_edit.setText(env.get("ZAI_BASE_URL", "") or env.get("LOCAL_CHAT_URL", ""))
        persona = env.get("PERSONA", "acido").lower()
        for index, (_label, code) in enumerate(PERSONA_LABELS):
            if code == persona:
                self.persona_combo.setCurrentIndex(index)
        try:
            self.history_spin.setValue(int(env.get("CHAT_HISTORY_TURNS", "8")))
        except ValueError:
            self.history_spin.setValue(8)
        self.tts_edit.setText(env.get("TTS_VOICE", "es-ES-ElviraNeural"))
        self.stt_combo.setCurrentIndex(1 if env.get("STT_PROVIDER", "google") == "whisper" else 0)
        self.actions_check.setChecked(bool(value("actions/enabled")))
        self.persist_check.setChecked(bool(value("chat/persist")))

    def _provider_changed(self):
        _label, code, _key, model, has_base = PROVIDERS[self.provider_combo.currentIndex()]
        if not self.model_edit.text().strip():
            self.model_edit.setText(model)
        self.base_url_edit.setVisible(has_base)
        self.key_edit.setEnabled(bool(_provider_key(code)))

    def _current_provider(self):
        return PROVIDERS[self.provider_combo.currentIndex()]

    # ---- Prueba de conexión ----

    def _probe(self):
        if self.probe_worker is not None and self.probe_worker.isRunning():
            return
        self.probe_btn.setEnabled(False)
        self.status_label.setText("Probando conexión...")
        self.probe_worker = ProbeWorker(self._env_updates())
        self.probe_worker.done.connect(self._probe_done)
        self.probe_worker.start()

    def _probe_done(self, ok: bool, message: str):
        self.probe_btn.setEnabled(True)
        self.status_label.setText(
            f"{'✅ Conexión OK' if ok else '❌ Sin conexión'} — {message}"
        )

    # ---- Guardado ----

    def _env_updates(self) -> dict[str, str]:
        _label, code, key_name, _model, _base = self._current_provider()
        updates = {
            "AI_PROVIDER": code,
            "PERSONA": PERSONA_LABELS[self.persona_combo.currentIndex()][1],
            "CHAT_HISTORY_TURNS": str(self.history_spin.value()),
            "TTS_VOICE": self.tts_edit.text().strip() or "es-ES-ElviraNeural",
            "STT_PROVIDER": "whisper" if self.stt_combo.currentIndex() == 1 else "google",
        }
        for _l, provider_code, provider_key, _m, _b in PROVIDERS:
            if provider_key:
                updates[provider_key] = ""
        if key_name:
            updates[key_name] = self.key_edit.text().strip()
        model_key = _model_key(code)
        if self.model_edit.text().strip():
            updates[model_key] = self.model_edit.text().strip()
        base = self.base_url_edit.text().strip()
        if code == "zai":
            if base:
                updates["ZAI_BASE_URL"] = base
        elif code == "llamacpp":
            updates["LOCAL_CHAT_URL"] = base or "http://127.0.0.1:8080/v1/chat/completions"
        return updates

    def accept(self):
        key_name = self._current_provider()[2]
        if key_name and not self.key_edit.text().strip():
            self.status_label.setText("⚠️ Ese proveedor necesita una clave de API.")
            return
        try:
            envfile.update_env(self._env_updates())
        except OSError as exc:
            self.status_label.setText(f"❌ No se pudo guardar .env: {exc}")
            return
        set_value("actions/enabled", self.actions_check.isChecked())
        set_value("chat/persist", self.persist_check.isChecked())
        set_value("setup/done", True)
        super().accept()


def _model_key(provider: str) -> str:
    return {
        "zai": "ZAI_MODEL",
        "openai": "OPENAI_MODEL",
        "gemini": "GEMINI_MODEL",
        "ollama": "LOCAL_LLM_MODEL",
        "lmstudio": "LOCAL_LLM_MODEL",
        "llamacpp": "LOCAL_LLM_MODEL",
    }[provider]


def _provider_key(provider: str) -> str:
    for _label, code, key, _model, _base in PROVIDERS:
        if code == provider:
            return key
    return ""
