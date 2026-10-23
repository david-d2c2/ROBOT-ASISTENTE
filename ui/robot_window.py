"""Ventana del robot: estados, interacción, bandeja y ciclo de vida."""
import html
import logging
import math
import os
import re
import time

from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import QCloseEvent, QIcon, QPixmap, QTextCursor
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QMenu, QSystemTrayIcon, QTextBrowser,
    QGraphicsDropShadowEffect
)

from core import app_settings, envfile
from core.ai_engine import AIEngine
from core.chat_store import ChatStore
from core.single_instance import start_instance_server
from core.version import APP_NAME
from core.voice_engine import VoiceEngine
from core.worker import AIWorker
from ui import theme
from ui.painters import RobotPaintingMixin
from ui.settings_dialog import SettingsDialog

log = logging.getLogger(__name__)

ROBOT_HEIGHT_MIN = 90
ROBOT_HEIGHT_MAX = 200


class DesktopRobot(RobotPaintingMixin, QWidget):
    ROBOT_DRAW_HEIGHT = 120
    ROBOT_VIEWBOX_W = 200.0
    ROBOT_VIEWBOX_H = 172.0
    # Fracciones sobre el sprite 3D (512x512) para animar encima del render.
    SPRITE_FACE = (100.8, 176.7, 316.6, 192.7)   # pantalla de cara: x, y, w, h
    SPRITE_ANTENNA = (257.0, 36.0, 22.0)          # bola de antena: cx, cy, radio

    def __init__(self):
        super().__init__()
        self.ai = AIEngine()
        self.voice = VoiceEngine()
        self.speech_enabled = True
        self.worker = None
        self._retired = []
        self.history = []
        self._closing = False
        self._quitting = False
        self._answer_received = False
        self._had_error = False

        self.state = "MOVING"
        self.direction = 1  # 1 derecha, -1 izquierda
        self.speed = 3
        self.wheel_angle = 0
        self.animation_tick = 0
        self.blink_counter = 0
        self.is_blinking = False
        self.hovered = False
        self.drag_pos = None
        self.reduced_motion = app_settings.env("REDUCED_MOTION").lower() in ("1", "true", "yes", "on")
        self.chat_messages: list[dict] = []
        self._status_text: str | None = None
        self.chat_store = ChatStore()

        self.init_sprite()
        self.init_ui()
        self.init_timers()
        self._restore_persisted_chat()
        self._maybe_start_setup_wizard()

    # ---- Recursos ----

    def init_sprite(self):
        sprite_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets", "sprites3d", "robot-3d.png",
        )
        self.robot_sprite = QPixmap(sprite_path) if os.path.exists(sprite_path) else None
        if self.robot_sprite is None:
            svg_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "assets", "robot-body.svg",
            )
            self.body_svg = QSvgRenderer(svg_path)
            if not self.body_svg.isValid():
                raise RuntimeError(f"No se pudo cargar el cuerpo del robot: {svg_path}")
            log.info("Sprite 3D no disponible; usando dibujo vectorial de respaldo")

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFixedWidth(340)
        self.ROBOT_DRAW_HEIGHT = max(
            ROBOT_HEIGHT_MIN, min(ROBOT_HEIGHT_MAX,
                                  int(app_settings.value("window/robot_height") or 120))
        )

        screen = QApplication.primaryScreen().availableGeometry()
        self.screen_left = screen.left()
        self.screen_right = screen.right() - self.width()
        self.screen_bottom = screen.bottom()

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, self.ROBOT_DRAW_HEIGHT + 6)
        self.main_layout.setSpacing(6)
        self.main_layout.addStretch(1)

        self.bubble = QTextBrowser()
        self.bubble.setOpenExternalLinks(True)
        self.bubble.setFixedHeight(130)
        self.bubble.setAccessibleName("Conversación con el robot")
        self.bubble.setStyleSheet(theme.CHAT_QSS)
        bubble_glow = QGraphicsDropShadowEffect(self)
        bubble_glow.setBlurRadius(14)
        bubble_glow.setColor(theme.CYAN)
        bubble_glow.setOffset(0, 0)
        self.bubble.setGraphicsEffect(bubble_glow)
        self.main_layout.addWidget(self.bubble)

        self.input_container = QWidget()
        input_layout = QHBoxLayout(self.input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(4)

        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Escribe algo...")
        self.text_input.setStyleSheet(theme.INPUT_QSS)
        self.text_input.returnPressed.connect(self.send_text)

        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setFixedSize(34, 28)
        self.mic_btn.setToolTip("Hablar por micrófono")
        self.mic_btn.setStyleSheet(theme.MIC_QSS)
        self.mic_btn.clicked.connect(self.start_listening)

        self.stop_btn = QPushButton("⏹")
        self.stop_btn.setFixedSize(34, 28)
        self.stop_btn.setToolTip("Detener la consulta en curso")
        self.stop_btn.setAccessibleName("Detener consulta")
        self.stop_btn.setStyleSheet(theme.STOP_QSS)
        self.stop_btn.clicked.connect(self.cancel_current)
        self.stop_btn.hide()

        self.close_btn = QPushButton("✖")
        self.close_btn.setFixedSize(34, 28)
        self.close_btn.setToolTip("Ocultar (el robot sigue en la bandeja); apaga desde el menú contextual o la bandeja")
        self.close_btn.setStyleSheet(theme.CLOSE_QSS)
        self.close_btn.clicked.connect(self.close)

        self.voice_btn = QPushButton("Voz")
        self.voice_btn.setCheckable(True)
        self.voice_btn.setChecked(True)
        self.voice_btn.setFixedSize(42, 28)
        self.voice_btn.setToolTip("Leer respuestas con Microsoft (Internet)")
        self.voice_btn.setAccessibleName("Activar voz")
        self.voice_btn.setStyleSheet(theme.VOICE_QSS)
        self.voice_btn.toggled.connect(self.set_speech_enabled)

        self.mic_btn.setToolTip("Transcribir con Google (Internet); usa el micrófono predeterminado")
        self.mic_btn.setAccessibleName("Hablar por micrófono")
        self.close_btn.setAccessibleName("Ocultar o apagar el robot")

        input_layout.addWidget(self.text_input)
        input_layout.addWidget(self.mic_btn)
        input_layout.addWidget(self.stop_btn)
        input_layout.addWidget(self.voice_btn)
        input_layout.addWidget(self.close_btn)
        self.main_layout.addWidget(self.input_container)
        self.input_container.hide()

        self.init_tray()

        saved_settings = app_settings.settings()
        saved_x = saved_settings.value("window/x", 120, type=int)
        self.move(saved_x, self.screen_bottom - 260)
        self.anchor_to_ground()

        if not saved_settings.value("voice/enabled", True, type=bool):
            self.voice_btn.setChecked(False)

        app = QApplication.instance()
        app.screenAdded.connect(self._on_screens_changed)
        app.screenRemoved.connect(self._on_screens_changed)
        for screen in app.screens():
            screen.availableGeometryChanged.connect(self.anchor_to_ground)

    # ---- Bandeja ----

    def init_tray(self):
        self.tray = QSystemTrayIcon(
            QIcon(os.path.join(self.assets_dir(), "robot-assistant.ico"))
        )
        self.tray_menu = QMenu()
        show_action = self.tray_menu.addAction("Mostrar u ocultar el robot")
        self.tray_voice_action = self.tray_menu.addAction("Voz activada")
        self.tray_voice_action.setCheckable(True)
        self.tray_voice_action.setChecked(True)
        self.tray_voice_action.toggled.connect(self.voice_btn.setChecked)
        forget_action = self.tray_menu.addAction("Olvidar conversación")
        settings_action = self.tray_menu.addAction("⚙ Ajustes...")
        self.tray_menu.addSeparator()
        quit_action = self.tray_menu.addAction("Apagar robot")
        self.tray.setContextMenu(self.tray_menu)
        self.tray.setToolTip(APP_NAME)
        show_action.triggered.connect(self.toggle_visibility)
        forget_action.triggered.connect(self.forget_conversation)
        settings_action.triggered.connect(lambda: self._open_settings())
        quit_action.triggered.connect(self.quit_from_tray)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def on_tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.toggle_visibility()

    def quit_from_tray(self):
        self._quitting = True
        self.close()

    def start_single_instance_server(self):
        self._instance_server = start_instance_server(self.toggle_visibility)

    @staticmethod
    def assets_dir() -> str:
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"
        )

    # ---- Ajustes ----

    def _save_settings(self):
        saved = app_settings.settings()
        saved.setValue("window/x", self.x())
        saved.setValue("window/robot_height", self.ROBOT_DRAW_HEIGHT)
        saved.setValue("voice/enabled", self.speech_enabled)
        saved.sync()

    def _on_screens_changed(self, *args):
        for screen in QApplication.instance().screens():
            try:
                screen.availableGeometryChanged.disconnect(self.anchor_to_ground)
            except TypeError:
                pass
            screen.availableGeometryChanged.connect(self.anchor_to_ground)
        self.anchor_to_ground()

    def anchor_to_ground(self):
        center = self.frameGeometry().center()
        screen = QApplication.screenAt(center) or self.screen() or QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        self.screen_left = bounds.left()
        self.screen_right = max(bounds.left(), bounds.right() - self.width() + 1)
        self.screen_bottom = bounds.bottom() + 1
        self.main_layout.activate()
        target_height = min(bounds.height(), max(230, self.sizeHint().height()))
        current_x = max(self.screen_left, min(self.x(), self.screen_right))
        self.setFixedHeight(target_height)
        self.move(current_x, self.screen_bottom - target_height)

    # ---- Animación ----

    def init_timers(self):
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_physics)
        self.anim_timer.start(50)

    def update_physics(self):
        self.animation_tick += 1
        self.blink_counter += 1
        if self.blink_counter > 60:
            self.is_blinking = True
            if self.blink_counter > 64:
                self.is_blinking = False
                self.blink_counter = 0

        if self.state == "MOVING" and self.drag_pos is None and self.isVisible() and not self.reduced_motion:
            new_x = self.x() + (self.speed * self.direction)
            if new_x >= self.screen_right:
                self.direction = -1
            elif new_x <= self.screen_left:
                self.direction = 1
            self.move(max(self.screen_left, min(new_x, self.screen_right)), self.screen_bottom - self.height())
            self.wheel_angle = (self.wheel_angle + 10 * self.direction) % 360

        # Solo repinta la zona del robot: el resto de la ventana es estática.
        self.update(0, self.height() - self.ROBOT_DRAW_HEIGHT - 12, self.width(), self.ROBOT_DRAW_HEIGHT + 12)

    def showEvent(self, event):
        if not self.anim_timer.isActive():
            self.anim_timer.start(50)
        super().showEvent(event)

    def hideEvent(self, event):
        self.anim_timer.stop()
        super().hideEvent(event)

    def wheelEvent(self, event):
        if event.position().y() < self.height() - self.ROBOT_DRAW_HEIGHT - 6:
            event.ignore()
            return
        delta = 8 if event.angleDelta().y() > 0 else -8
        self.ROBOT_DRAW_HEIGHT = max(
            ROBOT_HEIGHT_MIN, min(ROBOT_HEIGHT_MAX, self.ROBOT_DRAW_HEIGHT + delta)
        )
        self.main_layout.setContentsMargins(10, 10, 10, self.ROBOT_DRAW_HEIGHT + 6)
        self.anchor_to_ground()
        self.update()
        event.accept()

    # ---- Eventos de ratón ----

    def enterEvent(self, event):
        self.hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered = False
        self.update()
        super().leaveEvent(event)

    def _toggle_controls(self):
        if self.input_container.isHidden():
            self.state = "IDLE"
            self.input_container.show()
            self.anchor_to_ground()
            self.text_input.setFocus()
        else:
            self.input_container.hide()
            self.state = "MOVING"
            self.anchor_to_ground()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.worker is not None:
                return
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            if event.position().y() >= self.height() - self.ROBOT_DRAW_HEIGHT - 6:
                self._toggle_controls()
        elif event.button() == Qt.MouseButton.RightButton:
            menu = QMenu(self)
            if self.input_container.isHidden():
                talk_action = menu.addAction("Hablar con el robot")
            else:
                talk_action = menu.addAction("Ocultar controles")
            forget_action = menu.addAction("Olvidar conversación")
            copy_action = menu.addAction("Copiar última respuesta")
            settings_action = menu.addAction("⚙ Ajustes...")
            menu.addSeparator()
            quit_action = menu.addAction("Apagar Robot")
            action = menu.exec(event.globalPosition().toPoint())
            if action == quit_action:
                self.close()
            elif action == talk_action and self.worker is None:
                self._toggle_controls()
            elif action == forget_action:
                self.forget_conversation()
            elif action == copy_action:
                self.copy_last_answer()
            elif action == settings_action:
                self._open_settings()

    def mouseReleaseEvent(self, event):
        was_dragging = self.drag_pos is not None
        self.drag_pos = None
        if was_dragging:
            self.anchor_to_ground()
        super().mouseReleaseEvent(event)

    # ---- Chat: render, mensajes y persistencia ----

    GREETING = "Bip-bip. ¿Qué? Haz clic en mí si necesitas algo... total, no tienes nada mejor que hacer."

    @staticmethod
    def _md_to_html(text: str) -> str:
        escaped = html.escape(text)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
        escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
        return escaped.replace("\n", "<br>")

    def _message_html(self, role: str, text: str) -> str:
        body = self._md_to_html(text)
        if role == "user":
            return (
                '<table width="100%" cellspacing="0" cellpadding="3"><tr>'
                '<td align="right"><span style="background-color:#0E3A46; color:#BFF7FF;">'
                f"&nbsp;{body}&nbsp;</span></td></tr></table>"
            )
        if role == "system":
            return f'<i style="color:#7E93A9;">{body}</i><br>'
        return (
            '<table width="100%" cellspacing="0" cellpadding="3"><tr>'
            '<td align="left"><span style="background-color:#101B2E; color:#8FF7FF;">'
            f"&nbsp;{body}&nbsp;</span></td></tr></table>"
        )

    def _render_chat(self):
        parts = [
            self._message_html(message["role"], message["text"])
            for message in self.chat_messages
        ]
        if self._status_text:
            parts.append(self._message_html("system", self._status_text))
        self.bubble.setHtml("".join(parts) or "&nbsp;")
        self._bubble_scroll_bottom()

    def _render_chat_soon(self):
        if not self._render_timer.isActive():
            self._render_timer.start()

    def last_message_text(self) -> str:
        if self._status_text:
            return self._status_text
        if self.chat_messages:
            return self.chat_messages[-1]["text"]
        return ""

    def _append_message(self, role: str, text: str):
        self.chat_messages.append({"role": role, "text": text})
        if len(self.chat_messages) > 60:
            self.chat_messages = self.chat_messages[-60:]
        self._render_chat()

    def _bubble_set_text(self, text: str):
        """Reemplaza la conversación visible por un único mensaje del sistema."""
        self.chat_messages = [{"role": "system", "text": text}]
        self._status_text = None
        self._render_chat()

    def _bubble_scroll_bottom(self):
        bar = self.bubble.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _restore_persisted_chat(self):
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(120)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._render_chat)
        if not app_settings.value("chat/persist"):
            self._append_message("system", self.GREETING)
            return
        recent = self.chat_store.load_recent(30)
        for role, text in recent:
            self.chat_messages.append({"role": role, "text": text})
        if recent:
            self.history = [
                {"role": role, "content": text}
                for role, text in self.chat_store.load_recent(40)
            ]
            self._append_message("system", "(Conversación anterior restaurada)")
        else:
            self._append_message("system", self.GREETING)

    def copy_last_answer(self):
        for message in reversed(self.chat_messages):
            if message["role"] == "assistant":
                QApplication.clipboard().setText(message["text"])
                self._append_message("system", "Respuesta copiada al portapapeles.")
                return
        self._append_message("system", "Aún no hay nada que copiar, figuren.")

    # ---- Burbuja: texto y scroll ----

    def _set_busy(self, busy: bool):
        self.text_input.setEnabled(not busy)
        self.mic_btn.setEnabled(not busy)
        if busy:
            self.mic_btn.hide()
            self.stop_btn.show()
        else:
            self.stop_btn.hide()
            self.mic_btn.show()

    def send_text(self):
        prompt = self.text_input.text().strip()
        if not prompt or self.worker is not None or self._closing:
            return
        self.text_input.clear()
        self.start_worker(prompt, use_mic=False)

    def start_listening(self):
        if self.worker is not None or self._closing:
            return
        self.start_worker("", use_mic=True)

    def start_worker(self, prompt, use_mic):
        self._answer_received = False
        self._had_error = False
        self.state = "LISTENING" if use_mic else "THINKING"
        self._status_text = "🎤 Habla ahora..." if use_mic else "Pensando..."
        if not use_mic:
            self._append_message("user", prompt)
        self._render_chat()
        self._set_busy(True)
        self.anchor_to_ground()
        self.worker = AIWorker(
            self.ai, self.voice, prompt, use_mic, self.speech_enabled,
            history=list(self.history),
        )
        self.worker.status_update.connect(self.on_status_update)
        self.worker.query_ready.connect(self.on_query_ready)
        self.worker.partial_ready.connect(self.on_partial)
        self.worker.answer_ready.connect(self.on_ai_response)
        self.worker.state_changed.connect(self.on_state_changed)
        self.worker.failed.connect(self.on_worker_error)
        self.worker.finished.connect(lambda w=self.worker: self.on_worker_finished(w))
        self.worker.start()

    def cancel_current(self):
        worker = self.worker
        if worker is None or self._closing:
            return
        self.worker = None
        self._retired.append(worker)
        worker.requestInterruption()
        # Evita que un resultado tardío pise el mensaje de cancelación.
        for signal in (
            worker.status_update, worker.partial_ready, worker.answer_ready,
            worker.state_changed, worker.failed,
        ):
            try:
                signal.disconnect()
            except TypeError:
                pass
        self.voice.stop()
        self.state = "IDLE"
        self._set_busy(False)
        self._bubble_set_text("Consulta cancelada. Más rápida que tu paciencia, eh.")
        self.anchor_to_ground()

    def forget_conversation(self):
        self.history = []
        self.chat_store.clear()
        if self.worker is None and not self._closing:
            self.state = "IDLE"
            self._bubble_set_text("Memoria borrada. Como si nada hubiera pasado... justo como yo con tus preguntas raras.")

    # ---- Ajustes ----

    def _maybe_start_setup_wizard(self):
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return  # tests/CI: nunca bloquear el bucle con un diálogo
        if app_settings.value("setup/done"):
            return
        env_values = envfile.read_env()
        has_key = any(
            env_values.get(key) for key in ("ZAI_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY")
        )
        if has_key:
            app_settings.set_value("setup/done", True)
        else:
            log.info("Primera ejecución sin clave configurada; abriendo asistente")
            QTimer.singleShot(800, lambda: self._open_settings(wizard=True))

    def _open_settings(self, wizard: bool = False):
        dialog = SettingsDialog(self, wizard=wizard)
        if dialog.exec():
            self._apply_settings()

    def _apply_settings(self):
        # Los workers en curso terminan con sus motores; los nuevos usan los nuevos.
        self.ai = AIEngine()
        self.voice = VoiceEngine()
        self.reduced_motion = app_settings.env("REDUCED_MOTION").lower() in ("1", "true", "yes", "on")
        log.info("Ajustes aplicados (proveedor=%s, persona=%s)", self.ai.provider, self.ai.persona)
        if self.worker is None and not self._closing:
            self.state = "IDLE"
            self._bubble_set_text("Ajustes aplicados. Vale, cerebro nuevo instalado... ¿qué quieres ahora?")

    def set_speech_enabled(self, enabled):
        self.speech_enabled = enabled
        if self.worker is not None:
            self.worker.speech_enabled = enabled
        if self.tray_voice_action.isChecked() != enabled:
            self.tray_voice_action.blockSignals(True)
            self.tray_voice_action.setChecked(enabled)
            self.tray_voice_action.blockSignals(False)

    def on_status_update(self, status_text: str):
        if not self._closing:
            self._status_text = status_text
            self._render_chat()

    def on_query_ready(self, query: str):
        if not self._closing:
            self._append_message("user", query)

    def on_partial(self, text: str):
        if self._closing or self.worker is None:
            return
        self._status_text = None
        if self.chat_messages and self.chat_messages[-1]["role"] == "assistant":
            self.chat_messages[-1]["text"] = text
        else:
            self.chat_messages.append({"role": "assistant", "text": text})
        self._render_chat_soon()

    def on_state_changed(self, state: str):
        if not self._closing:
            self.state = state

    def on_ai_response(self, response_text: str):
        if self._closing:
            return
        self._answer_received = True
        self._status_text = None
        if self.chat_messages and self.chat_messages[-1]["role"] == "assistant":
            self.chat_messages[-1]["text"] = response_text
        else:
            self.chat_messages.append({"role": "assistant", "text": response_text})
        self._render_chat()
        worker = self.worker
        if worker is not None:
            self.history.append({"role": "user", "content": worker.final_query})
            self.history.append({"role": "assistant", "content": response_text})
            if len(self.history) > 40:
                self.history = self.history[-40:]
            self.chat_store.append("user", worker.final_query)
            self.chat_store.append("assistant", response_text)
        self.anchor_to_ground()

    def on_worker_error(self, message: str):
        if self._closing:
            return
        self._had_error = True
        self.state = "ERROR"
        self._status_text = None
        if self._answer_received and self.chat_messages:
            last = self.chat_messages[-1]
            last["text"] = last["text"] + "\n" + message
        else:
            self.chat_messages.append({"role": "system", "text": message})
        self._render_chat()
        self.anchor_to_ground()

    def on_worker_finished(self, worker=None):
        if worker is None:
            worker = self.worker
        if worker is None:
            return
        worker.wait()
        if worker in self._retired:
            self._retired.remove(worker)
        worker.deleteLater()
        if worker is not self.worker:
            return
        self.worker = None
        if self._closing:
            self._quitting = True
            self.close()
            return
        self._set_busy(False)
        if self._had_error:
            self.state = "ERROR"
            QTimer.singleShot(1200, self.clear_error_state)
        else:
            self.state = "IDLE"
        self.anchor_to_ground()

    def clear_error_state(self):
        if not self._closing and self.worker is None and self.state == "ERROR":
            self.state = "IDLE"
            self.update()

    # ---- Cierre ----

    def closeEvent(self, event: QCloseEvent):
        if not self._quitting and QSystemTrayIcon.isSystemTrayAvailable():
            # El botón ✖ oculta el robot; el apagado real vive en la bandeja
            # y en el menú contextual ("Apagar Robot").
            event.ignore()
            self.hide()
            return
        if self.worker is not None or self._retired:
            self._closing = True
            for worker in [self.worker] + list(self._retired):
                if worker is not None:
                    worker.requestInterruption()
            self.voice.stop()
            self._bubble_set_text("Cerrando al terminar la operación en curso...")
            self.text_input.setEnabled(False)
            self.mic_btn.setEnabled(False)
            self.voice_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
            self.anim_timer.stop()
            event.ignore()
            self._wait_and_quit(time.monotonic() + 8.0)
            return
        self._save_settings()
        self.anim_timer.stop()
        self.tray.hide()
        event.accept()
        QApplication.instance().quit()

    def _wait_and_quit(self, deadline):
        busy = (self.worker is not None and self.worker.isRunning()) or any(
            worker.isRunning() for worker in self._retired
        )
        if busy and time.monotonic() < deadline:
            QTimer.singleShot(150, lambda: self._wait_and_quit(deadline))
            return
        if busy:
            # Hilos atrapados en E/S sin respuesta a la interrupción: salir en seco
            # para no dejar el proceso colgado tras el timeout.
            self._save_settings()
            log.warning("Hilos aún activos tras el timeout; cierre forzado")
            os._exit(0)
        self._save_settings()
        self.tray.hide()
        QApplication.instance().quit()
