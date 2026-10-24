"""Ventana del robot: estados, interacción, bandeja y ciclo de vida."""
import base64
import logging
import math
import os
import random
import threading
import time

from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import QCloseEvent, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QMenu, QMessageBox, QSystemTrayIcon, QTextBrowser,
    QGraphicsDropShadowEffect
)

from core import app_settings, envfile, updates
from core import actions as desktop_actions
from core.ai_engine import AIEngine
from core.chat_store import ChatStore
from core.hands_free import HandsFreeLoop
from core.single_instance import start_instance_server
from core.version import APP_NAME, __version__
from core.voice_engine import VoiceEngine
from core.worker import AIWorker
from ui import theme
from ui.capture_overlay import CaptureOverlay
from ui.chat_view import ChatView
from ui.painters import RobotPaintingMixin
from ui.settings_dialog import SettingsDialog
from ui.tray_controller import TrayController

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
    SPRITE_SIDE_WHEEL = (195.0, 425.0, 46.0)      # rueda visible de perfil: cx, cy, radio

    GREETING = "Bip-bip. ¿Qué? Haz clic en mí si necesitas algo... total, no tienes nada mejor que hacer."

    WALK_QUIPS = (
        "Ni me hables. Tú a lo tuyo.",
        "Te veo. No digo nada.",
        "Aquí, rodando e ignorándote con estilo.",
        "Bip-bip. Nada que declarar.",
        "Descanso táctico. No te acostumbres.",
        "Sigo en mis ruedas. Literalmente.",
        "¿Qué? Estaba de viaje...",
        "Momento de silencio por tu productividad.",
    )

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
        self._pending_image: str | None = None
        self._capture_overlay = None
        self.hands_free_loop = None
        self.chat_store = ChatStore()

        # Paseo: de perfil, con paradas para mirar de frente.
        self.walk_pose = "profile"   # "profile" (rodando) | "front" (parado, mirando)
        self._pose_ticks = 0
        self._pose_switch = 0        # transición de giro (encoge/estira)
        self._bubble_visible = True
        self._quip_busy = False      # hay una frase del paseo sonando
        self._plan_walk()

        self.init_sprite()
        self.init_ui()
        self.init_timers()
        self._restore_persisted_chat()
        self._restore_hands_free()
        self._maybe_start_setup_wizard()
        QTimer.singleShot(4000, lambda: self.check_for_updates(auto=True))

    # ---- Recursos ----

    def init_sprite(self):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        front_path = os.path.join(base, "assets", "sprites3d", "robot-3d.png")
        self.robot_sprite = QPixmap(front_path) if os.path.exists(front_path) else None
        side_path = os.path.join(base, "assets", "sprites3d", "robot-side.png")
        self.robot_side = QPixmap(side_path) if os.path.exists(side_path) else None
        self._side_mirrored: QPixmap | None = None
        if self.robot_sprite is None:
            svg_path = os.path.join(base, "assets", "robot-body.svg")
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

        self.bubble = ChatView(self)
        self.bubble.setFixedHeight(130)
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

        self.capture_btn = QPushButton("📷")
        self.capture_btn.setFixedSize(34, 28)
        self.capture_btn.setToolTip("Capturar una zona de la pantalla y preguntarle al robot")
        self.capture_btn.setAccessibleName("Capturar pantalla")
        self.capture_btn.setStyleSheet(theme.MIC_QSS)
        self.capture_btn.clicked.connect(self.start_capture)

        self.stop_btn = QPushButton("⏹")
        self.stop_btn.setFixedSize(34, 28)
        self.stop_btn.setToolTip("Detener la consulta en curso")
        self.stop_btn.setAccessibleName("Detener consulta")
        self.stop_btn.setStyleSheet(theme.STOP_QSS)
        self.stop_btn.clicked.connect(self.stop_clicked)
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
        input_layout.addWidget(self.capture_btn)
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
        self.tray_controller = TrayController(
            os.path.join(self.assets_dir(), "robot-assistant.ico"),
            APP_NAME,
            callbacks={
                "toggle_visibility": self.toggle_visibility,
                "toggle_voice": self.voice_btn.setChecked,
                "forget": self.forget_conversation,
                "copy_answer": self.copy_last_answer,
                "open_settings": lambda: self._open_settings(),
                "check_updates": self.check_for_updates,
                "about": self._show_about,
                "quit": self.quit_from_tray,
                "tray_activated": self.on_tray_activated,
                "version": __version__,
            },
        )
        self.hands_free_action = self.tray_controller.add_action(
            "👂 Modo manos libres", self.toggle_hands_free, checkable=True
        )

    @property
    def tray(self):
        return self.tray_controller.tray

    @property
    def tray_voice_action(self):
        return self.tray_controller.voice_action

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

    # ---- Manos libres ----

    def toggle_hands_free(self, checked: bool):
        if checked:
            if self.hands_free_loop is None:
                self.hands_free_loop = HandsFreeLoop(self.voice)
                self.hands_free_loop.command_ready.connect(self._on_hands_free_command)
                self.hands_free_loop.start()
                log.info("Manos libres: bucle iniciado")
                self._append_message(
                    "system",
                    "👂 Manos libres activado: di «robot» seguido de lo que quieras "
                    "(con STT local funciona sin conexión).",
                )
        else:
            if self.hands_free_loop is not None:
                self.hands_free_loop.stop()
                self.hands_free_loop = None
                self._append_message("system", "Manos libres desactivado.")
        app_settings.set_value("hands_free", checked)

    def _on_hands_free_command(self, command: str):
        if self._closing:
            return
        if command == "":
            self.tray_controller.notify(APP_NAME, "Te escucho...", 3000)
            return
        if self.worker is not None:
            log.info("Manos libres: comando ignorado, consulta en curso")
            return
        self.start_worker(command, use_mic=False)

    def _restore_hands_free(self):
        if app_settings.value("hands_free"):
            QTimer.singleShot(2000, lambda: self.hands_free_action.setChecked(True))

    # ---- Actualizaciones ----

    def check_for_updates(self, auto: bool = False):
        if auto and not updates.should_auto_check():
            return
        if auto:
            updates.mark_checked()

        def on_result(latest):
            if latest is None:
                if not auto:
                    self._append_message("system", "🔄 No he podido comprobar actualizaciones (¿sin Internet?).")
                return
            if updates.is_newer(latest, __version__):
                self.tray.showMessage(
                    APP_NAME,
                    f"Nueva versión {latest} disponible. Descárgala en GitHub → Releases.",
                    self.tray.icon(), 10000,
                )
                self._append_message("system", f"🔄 Nueva versión {latest} disponible en GitHub → Releases.")
            elif not auto:
                self._append_message("system", f"✅ Estás en la última versión ({__version__}).")

        self._update_worker = updates.check_in_background(on_result)

    def _show_about(self):
        QMessageBox.information(
            self,
            APP_NAME,
            f"{APP_NAME} v{__version__}\n\n"
            "Robot compañero de escritorio con IA, voz y humor ácido.\n"
            "Código y actualizaciones: github.com/david-d2c2/ROBOT-ASISTENTE",
        )

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

    # ---- Paseo de perfil con paradas para mirar de frente ----

    def _plan_walk(self):
        """Segundos caminando antes de pararse a mirar (6–14 s)."""
        self._pose_ticks = random.randrange(120, 280)

    def _front_pause_ticks(self):
        """Segundos mirando de frente (1,5–2,8 s)."""
        return random.randrange(30, 56)

    def _pose_switch_step(self):
        if self._pose_switch > 0:
            self._pose_switch -= 1

    def _speak_quip(self, text: str):
        """Dice la frase del paseo en voz alta, en segundo plano y sin solaparse."""
        if not self.speech_enabled or self.worker is not None or self._quip_busy:
            return
        self._quip_busy = True

        def talk():
            try:
                self.voice.speak(text)
            except Exception:
                log.info("No se pudo decir la frase del paseo", exc_info=True)
            finally:
                self._quip_busy = False

        threading.Thread(target=talk, daemon=True, name="quip-voice").start()

    def _update_bubble_visibility(self):
        """Rodando de perfil, sin burbuja; de frente o conversando, con ella."""
        rolling = (
            self.state == "MOVING"
            and self.walk_pose == "profile"
            and self.drag_pos is None
            and not self.reduced_motion
            and self.input_container.isHidden()
        )
        should_show = not rolling
        if should_show == self._bubble_visible:
            return
        self._bubble_visible = should_show
        self.bubble.setVisible(should_show)
        self.anchor_to_ground()

    def update_physics(self):
        self.animation_tick += 1
        self.blink_counter += 1
        if self.blink_counter > 60:
            self.is_blinking = True
            if self.blink_counter > 64:
                self.is_blinking = False
                self.blink_counter = 0
        self._pose_switch_step()
        self._update_bubble_visibility()

        if self.state == "MOVING" and self.drag_pos is None and self.isVisible() and not self.reduced_motion:
            if self.walk_pose == "profile":
                new_x = self.x() + (self.speed * self.direction)
                if new_x >= self.screen_right:
                    self.direction = -1
                elif new_x <= self.screen_left:
                    self.direction = 1
                self.move(max(self.screen_left, min(new_x, self.screen_right)), self.screen_bottom - self.height())
                self.wheel_angle = (self.wheel_angle + 10 * self.direction) % 360
                self._pose_ticks -= 1
                if self._pose_ticks <= 0:
                    # Se para y mira de frente un momento, con frase ácida dicha en voz alta.
                    self.walk_pose = "front"
                    self._pose_ticks = self._front_pause_ticks()
                    quip = random.choice(self.WALK_QUIPS)
                    self._solo_text = quip
                    self._update_bubble_visibility()
                    self._render_chat()
                    self._speak_quip(quip)
            else:
                self._pose_ticks -= 1
                if self._pose_ticks <= 0:
                    self.walk_pose = "profile"
                    self._solo_text = None
                    self._plan_walk()
                    self._pose_switch = 6

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
            self._solo_text = None
            self.voice.stop()  # corta la frase del paseo si estaba sonando
            self._render_chat()
            self.input_container.show()
            self.anchor_to_ground()
            self.text_input.setFocus()
        else:
            self.state = "MOVING"
            self.walk_pose = "profile"
            self._plan_walk()
            self.input_container.hide()
            self.anchor_to_ground()
        self._update_bubble_visibility()

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

    # ---- Chat: delegación en ChatView ----

    @property
    def chat_messages(self):
        return self.bubble.messages

    @property
    def _solo_text(self):
        return self.bubble.solo_text

    @_solo_text.setter
    def _solo_text(self, value):
        self.bubble.solo_text = value

    def _append_message(self, role: str, text: str):
        self.bubble.append_message(role, text)

    def _bubble_set_text(self, text: str):
        self.bubble.show_single(text)

    def _render_chat(self):
        self.bubble.render()

    def last_message_text(self) -> str:
        return self.bubble.last_message_text()

    def _restore_persisted_chat(self):
        if not app_settings.value("chat/persist"):
            self._append_message("system", self.GREETING)
            return
        recent = self.chat_store.load_recent(30)
        for role, text in recent:
            self.bubble.messages.append({"role": role, "text": text})
        if recent:
            self.history = [
                {"role": role, "content": text}
                for role, text in self.chat_store.load_recent(40)
            ]
            self._append_message("system", "(Conversación anterior restaurada)")
        else:
            self._append_message("system", self.GREETING)

    def copy_last_answer(self):
        copied = self.bubble.copy_last_answer()
        if copied:
            self._append_message("system", "Respuesta copiada al portapapeles.")
        else:
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
        if self.worker is not None or self._closing:
            return
        image = self._pending_image
        if not prompt and not image:
            return
        self.text_input.clear()
        self._pending_image = None
        if not prompt:
            prompt = "Analiza esta captura: ¿qué ves y qué destacarías?"
        self.start_worker(prompt, use_mic=False, image=image)

    # ---- Visión: captura de pantalla ----

    def start_capture(self):
        if self.worker is not None or self._closing or self._capture_overlay is not None:
            return
        log.info("Iniciando captura de pantalla")
        self._capture_overlay = CaptureOverlay.start_capture(
            self._on_region_captured, self._on_capture_cancelled
        )

    def _on_capture_cancelled(self):
        self._capture_overlay = None
        self._append_message("system", "Captura cancelada.")

    def _on_region_captured(self, pixmap):
        self._capture_overlay = None
        from PyQt6.QtCore import QBuffer, QIODevice
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "PNG")
        self._pending_image = base64.b64encode(bytes(buffer.data())).decode("ascii")
        log.info("Captura lista (%d KB)", len(self._pending_image) // 1024)
        if self.input_container.isHidden():
            self._toggle_controls()
        else:
            self.text_input.setFocus()
        self._append_message(
            "system", "📸 Captura lista. Escribe qué quieres saber de ella y pulsa Enter."
        )

    def start_listening(self):
        if self.worker is not None or self._closing:
            return
        self.start_worker("", use_mic=True)

    def start_worker(self, prompt, use_mic, image=None):
        self._answer_received = False
        self._had_error = False
        self.state = "LISTENING" if use_mic else "THINKING"
        self.bubble.set_status("🎤 Habla ahora..." if use_mic else "Pensando...")
        if not use_mic:
            self._append_message("user", ("📸 " if image else "") + prompt)
        self._render_chat()
        self._set_busy(True)
        self.anchor_to_ground()
        self.worker = AIWorker(
            self.ai, self.voice, prompt, use_mic, self.speech_enabled,
            history=list(self.history), image=image,
        )
        self.worker.status_update.connect(self.on_status_update)
        self.worker.query_ready.connect(self.on_query_ready)
        self.worker.partial_ready.connect(self.on_partial)
        self.worker.answer_ready.connect(self.on_ai_response)
        self.worker.state_changed.connect(self.on_state_changed)
        self.worker.failed.connect(self.on_worker_error)
        self.worker.finished.connect(lambda w=self.worker: self.on_worker_finished(w))
        self.worker.start()

    def stop_clicked(self):
        if self.state == "SPEAKING":
            self.hush_current()
        else:
            self.cancel_current()

    def hush_current(self):
        """Calla la voz sin cancelar la conversación ni la consulta."""
        if self.worker is None or self._closing:
            return
        if hasattr(self.worker, "hush"):
            self.worker.hush()
        self.voice.stop()
        self._append_message("system", "🤫 Callado. La respuesta queda escrita.")

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
            self.bubble.set_status(status_text)

    def on_query_ready(self, query: str):
        if not self._closing:
            self._append_message("user", query)

    def on_partial(self, text: str):
        if self._closing or self.worker is None:
            return
        self.bubble.update_partial(text)

    def on_state_changed(self, state: str):
        if not self._closing:
            self.state = state
            if state == "SPEAKING":
                self.stop_btn.setText("🔇")
                self.stop_btn.setToolTip("Callar (la respuesta queda escrita)")
                self.stop_btn.setAccessibleName("Callar respuesta")
            else:
                self.stop_btn.setText("⏹")
                self.stop_btn.setToolTip("Detener la consulta en curso")
                self.stop_btn.setAccessibleName("Detener consulta")

    def on_ai_response(self, response_text: str):
        if self._closing:
            return
        self._answer_received = True
        self.bubble.set_status(None)
        if self.bubble.messages and self.bubble.messages[-1]["role"] == "assistant":
            self.bubble.messages[-1]["text"] = response_text
        else:
            self.bubble.messages.append({"role": "assistant", "text": response_text})
        self.bubble.render()
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
        self._maybe_run_action(response_text)

    # ---- Acciones de escritorio ----

    def _maybe_run_action(self, response_text: str):
        if not app_settings.value("actions/enabled"):
            return
        action = desktop_actions.extract_action(response_text)
        if action is None:
            return
        kind = action.get("action")
        log.info("Acción solicitada: %s", action)
        if kind == "open_app" and str(action.get("app", "")).lower() not in desktop_actions.allowed_apps():
            self._append_message("system", "⛔ Esa app no está en la lista permitida (ajustes).")
            return
        if kind not in desktop_actions.always_allowed() and not self._confirm_action(action):
            self._append_message("system", "🚫 Acción denegada. Que quede entre nosotros.")
            return
        ok, message = desktop_actions.execute(action, self.tray)
        self._append_message("system", message)
        if not ok:
            self.state = "ERROR"
            QTimer.singleShot(1500, self.clear_error_state)

    def _confirm_action(self, action: dict) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("El robot pide permiso para:")
        box.setInformativeText(desktop_actions.describe(action))
        always = QCheckBox("Permitir siempre este tipo de acción")
        box.setCheckBox(always)
        box.addButton("Permitir", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Denegar", QMessageBox.ButtonRole.RejectRole)
        result = box.exec()
        if always.isChecked():
            desktop_actions.allow_kind(action.get("action"))
        return result == QMessageBox.ButtonRole.AcceptRole.value

    def on_worker_error(self, message: str):
        if self._closing:
            return
        self._had_error = True
        self.state = "ERROR"
        self.bubble.set_status(None)
        if self._answer_received and self.bubble.messages:
            self.bubble.mark_last_answer(message)
        else:
            self._append_message("system", message)
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
