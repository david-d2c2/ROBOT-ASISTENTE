import sys
import os
import math
import time
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QRectF, QPointF, QSettings, QLockFile
)
from PyQt6.QtGui import (
    QPainter, QColor, QRadialGradient, QBrush, QPen, QFont, QIcon, QTextCursor,
    QPixmap
)
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QPlainTextEdit, QMenu, QSystemTrayIcon,
    QGraphicsDropShadowEffect, QMessageBox
)

SINGLE_INSTANCE_NAME = "robot-asistente"
from core.ai_engine import AIEngine, AIError
from core.voice_engine import VoiceEngine

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
            self.answer_ready.emit(answer)
        except AIError as error:
            self.failed.emit(str(error))
            return
        except Exception:
            self.failed.emit("No pude completar la consulta. Comprueba la conexión y la configuración.")
            return

        if self.speech_enabled and not self.isInterruptionRequested():
            self.state_changed.emit("SPEAKING")
            try:
                self.voice.speak(answer, should_stop=lambda: self.isInterruptionRequested() or not self.speech_enabled)
            except Exception:
                self.failed.emit("La respuesta está escrita, pero no pude reproducir la voz.")


class DesktopRobot(QWidget):
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
        self.worker = None
        self._retired = []
        self.history = []
        self._closing = False
        self._quitting = False
        self.speech_enabled = True
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

        self.init_sprite()
        self.init_ui()
        self.init_timers()

    def init_sprite(self):
        sprite_path = os.path.join(
            os.path.dirname(__file__), "assets", "sprites3d", "robot-3d.png"
        )
        self.robot_sprite = QPixmap(sprite_path) if os.path.exists(sprite_path) else None

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFixedWidth(340)

        svg_path = os.path.join(os.path.dirname(__file__), "assets", "robot-body.svg")
        self.body_svg = QSvgRenderer(svg_path)
        if not self.body_svg.isValid():
            raise RuntimeError(f"No se pudo cargar el cuerpo del robot: {svg_path}")

        screen = QApplication.primaryScreen().availableGeometry()
        self.screen_left = screen.left()
        self.screen_right = screen.right() - self.width()
        self.screen_bottom = screen.bottom()

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, self.ROBOT_DRAW_HEIGHT + 6)
        self.main_layout.setSpacing(6)
        self.main_layout.addStretch(1)

        self.bubble = QPlainTextEdit("Bip-bip. ¿Qué? Haz clic en mí si necesitas algo... total, no tienes nada mejor que hacer.")
        self.bubble.setReadOnly(True)
        self.bubble.setFixedHeight(110)
        self.bubble.setAccessibleName("Respuesta del robot")
        self.bubble.setFont(QFont("Segoe UI", 9))
        self.bubble.setStyleSheet(
            "QPlainTextEdit {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "   stop:0 rgba(8, 14, 26, 242), stop:1 rgba(12, 24, 42, 226));"
            " color: #8FF7FF;"
            " border: 1px solid rgba(0, 240, 255, 110);"
            " border-left: 3px solid #00F0FF;"
            " border-radius: 12px;"
            " padding: 8px 10px;"
            " }"
        )
        bubble_glow = QGraphicsDropShadowEffect(self)
        bubble_glow.setBlurRadius(14)
        bubble_glow.setColor(QColor(0, 240, 255, 60))
        bubble_glow.setOffset(0, 0)
        self.bubble.setGraphicsEffect(bubble_glow)
        self.main_layout.addWidget(self.bubble)

        self.input_container = QWidget()
        input_layout = QHBoxLayout(self.input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(4)

        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Escribe algo...")
        self.text_input.setStyleSheet(
            "QLineEdit {"
            " background: rgba(6, 12, 24, 235);"
            " color: #CFF9FF;"
            " border: 1px solid rgba(0, 240, 255, 90);"
            " border-radius: 14px;"
            " padding: 5px 10px;"
            " selection-background-color: #00F0FF;"
            " selection-color: #04141C;"
            " }"
            "QLineEdit:focus { border: 1px solid #00F0FF; background: rgba(10, 20, 36, 245); }"
        )
        self.text_input.returnPressed.connect(self.send_text)

        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setFixedSize(34, 28)
        self.mic_btn.setToolTip("Hablar por micrófono")
        self.mic_btn.setStyleSheet(
            "QPushButton {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "   stop:0 #12E4FF, stop:1 #00A9C2);"
            " color: #03202B;"
            " border: 1px solid rgba(255, 255, 255, 80);"
            " border-radius: 10px;"
            " font-weight: bold;"
            " }"
            "QPushButton:hover { background: #35EBFF; }"
            "QPushButton:pressed { background: #0093AB; }"
            "QPushButton:disabled { background: #35414E; color: #6B7A88; border-color: rgba(90,110,125,120); }"
        )
        self.mic_btn.clicked.connect(self.start_listening)

        self.stop_btn = QPushButton("⏹")
        self.stop_btn.setFixedSize(34, 28)
        self.stop_btn.setToolTip("Detener la consulta en curso")
        self.stop_btn.setAccessibleName("Detener consulta")
        self.stop_btn.setStyleSheet(
            "QPushButton {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "   stop:0 #FFB020, stop:1 #FF7A00);"
            " color: #2B1400;"
            " border: 1px solid rgba(255, 255, 255, 80);"
            " border-radius: 10px;"
            " font-weight: bold;"
            " }"
            "QPushButton:hover { background: #FFC24D; }"
            "QPushButton:disabled { background: #35414E; color: #6B7A88; border-color: rgba(90,110,125,120); }"
        )
        self.stop_btn.clicked.connect(self.cancel_current)
        self.stop_btn.hide()

        self.close_btn = QPushButton("✖")
        self.close_btn.setFixedSize(34, 28)
        self.close_btn.setToolTip("Ocultar (el robot sigue en la bandeja); apaga desde el menú contextual o la bandeja")
        self.close_btn.setStyleSheet(
            "QPushButton {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "   stop:0 #FF6B6B, stop:1 #D93131);"
            " color: white;"
            " border: none;"
            " border-radius: 10px;"
            " font-weight: bold;"
            " }"
            "QPushButton:hover { background: #FF8585; }"
            "QPushButton:pressed { background: #B92626; }"
        )
        self.close_btn.clicked.connect(self.close)

        self.voice_btn = QPushButton("Voz")
        self.voice_btn.setCheckable(True)
        self.voice_btn.setChecked(True)
        self.voice_btn.setFixedSize(42, 28)
        self.voice_btn.setToolTip("Leer respuestas con Microsoft (Internet)")
        self.voice_btn.setAccessibleName("Activar voz")
        self.voice_btn.setStyleSheet(
            "QPushButton {"
            " background: rgba(10, 18, 32, 235);"
            " color: #7DE8F7;"
            " border: 1px solid rgba(0, 240, 255, 110);"
            " border-radius: 10px;"
            " font-weight: 600;"
            " font-size: 8pt;"
            " }"
            "QPushButton:hover { border: 1px solid #00F0FF; color: #B9F8FF; }"
            "QPushButton:checked { background: rgba(0, 240, 255, 38); border: 1px solid #00F0FF; color: #E4FDFF; }"
            "QPushButton:disabled { color: #5B6B7A; border-color: rgba(90, 110, 125, 120); }"
        )
        self.voice_btn.toggled.connect(self.set_speech_enabled)
        self.mic_btn.setToolTip("Transcribir con Google (Internet); usa el micrófono predeterminado")
        self.mic_btn.setAccessibleName("Hablar por micrófono")
        self.close_btn.setAccessibleName("Ocultar o apagar el robot")
        self.close_btn.setToolTip("Ocultar (el robot sigue en la bandeja); apaga desde el menú contextual o la bandeja")

        input_layout.addWidget(self.text_input)
        input_layout.addWidget(self.mic_btn)
        input_layout.addWidget(self.stop_btn)
        input_layout.addWidget(self.voice_btn)
        input_layout.addWidget(self.close_btn)
        self.main_layout.addWidget(self.input_container)
        self.input_container.hide()

        self.init_tray()

        settings = QSettings("RobotAsistente", "RobotAsistente")
        saved_x = settings.value("window/x", 120, type=int)
        self.move(saved_x, self.screen_bottom - 260)
        self.anchor_to_ground()

        if not settings.value("voice/enabled", True, type=bool):
            self.voice_btn.setChecked(False)

        app = QApplication.instance()
        app.screenAdded.connect(self._on_screens_changed)
        app.screenRemoved.connect(self._on_screens_changed)
        for screen in app.screens():
            screen.availableGeometryChanged.connect(self.anchor_to_ground)

    def start_single_instance_server(self):
        """Atiende a lanzamientos posteriores: los traen a este robot a primer plano."""
        QLocalServer.removeServer(SINGLE_INSTANCE_NAME)
        self._instance_server = QLocalServer(self)
        self._instance_server.newConnection.connect(self._on_instance_connection)
        self._instance_server.listen(SINGLE_INSTANCE_NAME)

    def _on_instance_connection(self):
        socket = self._instance_server.nextPendingConnection()
        if socket is not None:
            socket.disconnectFromServer()
        self.show()
        self.raise_()
        self.activateWindow()

    def init_tray(self):
        self.tray = QSystemTrayIcon(
            QIcon(os.path.join(os.path.dirname(__file__), "assets", "robot-assistant.ico"))
        )
        self.tray_menu = QMenu()
        show_action = self.tray_menu.addAction("Mostrar u ocultar el robot")
        self.tray_voice_action = self.tray_menu.addAction("Voz activada")
        self.tray_voice_action.setCheckable(True)
        self.tray_voice_action.setChecked(True)
        self.tray_voice_action.toggled.connect(self.voice_btn.setChecked)
        forget_action = self.tray_menu.addAction("Olvidar conversación")
        self.tray_menu.addSeparator()
        quit_action = self.tray_menu.addAction("Apagar robot")
        self.tray.setContextMenu(self.tray_menu)
        self.tray.setToolTip("Robot Asistente")
        show_action.triggered.connect(self.toggle_visibility)
        forget_action.triggered.connect(self.forget_conversation)
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

    def _save_settings(self):
        settings = QSettings("RobotAsistente", "RobotAsistente")
        settings.setValue("window/x", self.x())
        settings.setValue("voice/enabled", self.speech_enabled)
        settings.sync()

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

        if self.state == "MOVING" and self.drag_pos is None and self.isVisible():
            new_x = self.x() + (self.speed * self.direction)
            if new_x >= self.screen_right:
                self.direction = -1
            elif new_x <= self.screen_left:
                self.direction = 1
            self.move(max(self.screen_left, min(new_x, self.screen_right)), self.screen_bottom - self.height())
            self.wheel_angle = (self.wheel_angle + 10 * self.direction) % 360

        self.update()

    # ---- Dibujo del robot: cuerpo SVG + ojos, antena y efectos programáticos ----

    def _state_color(self):
        return {
            "ERROR": QColor(255, 75, 90),
            "LISTENING": QColor(0, 255, 140),
            "SPEAKING": QColor(170, 120, 255),
        }.get(self.state, QColor(0, 240, 255))

    def _body_bob(self, phase):
        if self.state == "SPEAKING":
            return int(math.sin(phase * 2) * 2)
        if self.state == "IDLE":
            return int(math.sin(phase) * 2)
        return 0

    def _draw_shadow(self, painter, origin_x, origin_y, scale):
        rect = QRectF(origin_x + 44 * scale, origin_y + 158 * scale, 112 * scale, 16 * scale)
        grad = QRadialGradient(rect.center(), rect.width() / 2)
        grad.setColorAt(0.0, QColor(0, 0, 0, 80))
        grad.setColorAt(0.7, QColor(0, 0, 0, 40))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(rect)

    def _draw_halo(self, painter, origin_x, origin_y, scale, phase):
        pulse = 54 + (math.sin(phase * 2) + 1) * 4
        center = QPointF(origin_x + 100 * scale, origin_y + 73 * scale)
        radius = pulse * scale
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(0, 255, 140, 135), 3))
        painter.drawEllipse(center, radius, radius)

    def _draw_body(self, painter, origin_x, origin_y, robot_w, bob):
        self.body_svg.render(
            painter, QRectF(origin_x, origin_y + bob, robot_w, self.ROBOT_DRAW_HEIGHT)
        )

    def _draw_wheel_spokes(self, painter):
        angle = math.radians(self.wheel_angle)
        dx = math.cos(angle) * 5.5
        dy = math.sin(angle) * 5.5
        painter.setPen(QPen(QColor(126, 145, 169), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for hub_x in (66.0, 134.0):
            painter.drawLine(QPointF(hub_x - dx, 142 - dy), QPointF(hub_x + dx, 142 + dy))

    def _draw_antenna_light(self, painter):
        color = self._state_color()
        center = QPointF(100, 5.5)
        glow = QRadialGradient(center, 9)
        glow.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 130))
        glow.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, 9, 9)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(center, 5.5, 5.5)

    def _eye_glint(self, painter, cx, cy):
        painter.save()
        painter.setBrush(QBrush(QColor(255, 255, 255, 210)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), 3, 3)
        painter.restore()

    def _draw_face(self, painter, phase):
        color = self._state_color()
        look_x = 4 * self.direction if self.state == "MOVING" else (2 if self.hovered else 0)
        look_y = -2 if self.hovered else 0

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))

        if self.state == "ERROR":
            pen = QPen(color, 4.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for eye_cx in (78.0, 122.0):
                painter.drawLine(QPointF(eye_cx - 7.5, 66 + look_y), QPointF(eye_cx + 7.5, 80 + look_y))
                painter.drawLine(QPointF(eye_cx + 7.5, 66 + look_y), QPointF(eye_cx - 7.5, 80 + look_y))
            return

        if self.state == "THINKING":
            offset_y = math.sin(phase * 2) * 4
            painter.drawEllipse(QRectF(70, 65 + offset_y + look_y, 16, 16))
            self._eye_glint(painter, 74.5, 69.5 + offset_y + look_y)
            painter.drawEllipse(QRectF(114, 69 - offset_y + look_y, 12, 12))
            self._eye_glint(painter, 117, 72 - offset_y + look_y)
        elif self.state == "LISTENING":
            size = 15 + (math.sin(phase * 2) + 1) * 2.5
            for eye_cx in (78.0, 122.0):
                painter.drawEllipse(QRectF(eye_cx - size / 2 + look_x, 73 - size / 2 + look_y, size, size))
                self._eye_glint(painter, eye_cx - size / 5, 73 - size / 5 + look_y)
        elif self.state == "SPEAKING":
            height = 13 + (math.sin(phase * 3) + 1) * 6
            for eye_cx in (69.5, 113.5):
                painter.drawRoundedRect(QRectF(eye_cx + look_x, 73 - height / 2 + look_y, 17, height), 8.5, 8.5)
                self._eye_glint(painter, eye_cx + 4 + look_x, 73 - height / 4 + look_y)
        else:
            if self.is_blinking:
                for eye_cx in (69.5, 113.5):
                    painter.drawRoundedRect(QRectF(eye_cx + look_x, 71.5 + look_y, 17, 4), 2, 2)
            else:
                for eye_cx in (69.5, 113.5):
                    painter.drawRoundedRect(QRectF(eye_cx + look_x, 60.5 + look_y, 17, 25), 8.5, 8.5)
                    self._eye_glint(painter, eye_cx + 4 + look_x, 67.5 + look_y)

    def _draw_voice_bars(self, painter, base_x, base_y, scale, phase):
        color = self._state_color()
        painter.setPen(QPen(color, max(3.0, 4 * scale), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for index, height in enumerate((9, 15, 9)):
            wave = (height + math.sin(phase * 3 + index) * 3.5) * scale
            x = base_x + index * 9 * scale
            painter.drawLine(QPointF(x, base_y - wave / 2), QPointF(x, base_y + wave / 2))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        phase = self.animation_tick * 0.18
        if self.robot_sprite is not None:
            self._paint_sprite_robot(painter, phase)
        else:
            self._paint_vector_robot(painter, phase)

    # ---- Robot 3D: render generado + ojos y antena animados por encima ----

    def _paint_sprite_robot(self, painter, phase):
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        size = self.ROBOT_DRAW_HEIGHT * 0.96
        origin_x = self.width() / 2 - size / 2
        origin_y = self.height() - self.ROBOT_DRAW_HEIGHT + (self.ROBOT_DRAW_HEIGHT - size)
        bob = self._body_bob(phase)

        shadow_center_y = origin_y + size - 6
        shadow = QRadialGradient(QPointF(origin_x + size / 2, shadow_center_y), size * 0.48)
        shadow.setColorAt(0.0, QColor(0, 0, 0, 80))
        shadow.setColorAt(0.7, QColor(0, 0, 0, 40))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(shadow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            QPointF(origin_x + size / 2, shadow_center_y), size * 0.48, size * 0.11
        )

        if self.state == "LISTENING":
            fx, fy, fw, fh = self.SPRITE_FACE
            center = QPointF(origin_x + (fx + fw / 2) * size / 512.0,
                             origin_y + bob + (fy + fh / 2) * size / 512.0)
            radius = size * (0.72 + (math.sin(phase * 2) + 1) * 0.05)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(0, 255, 140, 135), 2.5))
            painter.drawEllipse(center, radius, radius)

        painter.drawPixmap(
            QRectF(origin_x, origin_y + bob, size, size),
            self.robot_sprite,
            QRectF(self.robot_sprite.rect()),
        )

        painter.save()
        painter.translate(origin_x, origin_y + bob)
        painter.scale(size / 512.0, size / 512.0)
        self._draw_sprite_antenna(painter)
        self._draw_sprite_face(painter, phase)
        painter.restore()

        if self.state == "SPEAKING":
            fx, fy, fw, fh = self.SPRITE_FACE
            self._draw_voice_bars(
                painter, origin_x + size + 8, origin_y + bob + (fy + fh / 2) * size / 512.0,
                1.0, phase,
            )

    def _draw_sprite_antenna(self, painter):
        color = self._state_color()
        center = QPointF(*self.SPRITE_ANTENNA[:2])
        glow = QRadialGradient(center, self.SPRITE_ANTENNA[2] * 1.9)
        glow.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 130))
        glow.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, self.SPRITE_ANTENNA[2] * 1.9, self.SPRITE_ANTENNA[2] * 1.9)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(center, self.SPRITE_ANTENNA[2], self.SPRITE_ANTENNA[2])

    def _draw_sprite_face(self, painter, phase):
        color = self._state_color()
        fx, fy, fw, fh = self.SPRITE_FACE
        center_y = fy + fh / 2
        look_x = 8 * self.direction if self.state == "MOVING" else (5 if self.hovered else 0)
        look_y = -5 if self.hovered else 0

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))

        if self.state == "ERROR":
            pen = QPen(color, 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for eye_cx in (fw * 0.261 + fx, fw * 0.739 + fx):
                painter.drawLine(
                    QPointF(eye_cx - 19, center_y - 14 + look_y),
                    QPointF(eye_cx + 19, center_y + 14 + look_y),
                )
                painter.drawLine(
                    QPointF(eye_cx + 19, center_y - 14 + look_y),
                    QPointF(eye_cx - 19, center_y + 14 + look_y),
                )
            return

        def glint(cx, cy):
            painter.save()
            painter.setBrush(QBrush(QColor(255, 255, 255, 210)))
            painter.drawEllipse(QPointF(cx, cy), 8, 8)
            painter.restore()
            painter.setBrush(QBrush(color))

        if self.state == "THINKING":
            offset_y = math.sin(phase * 2) * 12
            for eye_cx, radius, direction in ((fx + fw * 0.261, 26, 1), (fx + fw * 0.739, 20, -1)):
                cy = center_y + direction * offset_y + look_y
                painter.drawEllipse(QPointF(eye_cx + look_x, cy), radius, radius)
                glint(eye_cx + look_x - radius / 3, cy - radius / 3)
        elif self.state == "LISTENING":
            radius = 24 + (math.sin(phase * 2) + 1) * 5
            for eye_cx in (fx + fw * 0.261, fx + fw * 0.739):
                painter.drawEllipse(QPointF(eye_cx + look_x, center_y + look_y), radius, radius)
                glint(eye_cx + look_x - radius / 3, center_y + look_y - radius / 3)
        elif self.state == "SPEAKING":
            height = 56 + (math.sin(phase * 3) + 1) * 16
            for eye_cx in (fx + fw * 0.261, fx + fw * 0.739):
                painter.drawRoundedRect(
                    QRectF(eye_cx + look_x - 21, center_y + look_y - height / 2, 42, height),
                    21, 21,
                )
                glint(eye_cx + look_x - 8, center_y + look_y - height / 4)
        else:
            if self.is_blinking:
                for eye_cx in (fx + fw * 0.261, fx + fw * 0.739):
                    painter.drawRoundedRect(
                        QRectF(eye_cx + look_x - 26, center_y + look_y - 5, 52, 10), 5, 5
                    )
            else:
                for eye_cx in (fx + fw * 0.261, fx + fw * 0.739):
                    painter.drawEllipse(QPointF(eye_cx + look_x, center_y + look_y), 29, 29)
                    glint(eye_cx + look_x - 9, center_y + look_y - 10)

    # ---- Robot vectorial de respaldo (si no existe el sprite 3D) ----

    def _paint_vector_robot(self, painter, phase):
        scale = self.ROBOT_DRAW_HEIGHT / self.ROBOT_VIEWBOX_H
        robot_w = self.ROBOT_VIEWBOX_W * scale
        origin_x = self.width() / 2 - robot_w / 2
        origin_y = self.height() - self.ROBOT_DRAW_HEIGHT
        phase = self.animation_tick * 0.18
        bob = self._body_bob(phase)

        self._draw_shadow(painter, origin_x, origin_y, scale)
        if self.state == "LISTENING":
            self._draw_halo(painter, origin_x, origin_y, scale, phase)
        self._draw_body(painter, origin_x, origin_y, robot_w, bob)

        painter.save()
        painter.translate(origin_x, origin_y + bob)
        painter.scale(scale, scale)
        self._draw_wheel_spokes(painter)
        self._draw_antenna_light(painter)
        self._draw_face(painter, phase)
        painter.restore()

        if self.state == "SPEAKING":
            self._draw_voice_bars(
                painter, origin_x + robot_w + 9 * scale, origin_y + bob + 73 * scale, scale, phase
            )

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
            menu.addSeparator()
            quit_action = menu.addAction("Apagar Robot")
            action = menu.exec(event.globalPosition().toPoint())
            if action == quit_action:
                self.close()
            elif action == talk_action and self.worker is None:
                self._toggle_controls()
            elif action == forget_action:
                self.forget_conversation()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_pos:
            new_pos = event.globalPosition().toPoint() - self.drag_pos
            self.move(max(self.screen_left, min(new_pos.x(), self.screen_right)), self.screen_bottom - self.height())

    def mouseReleaseEvent(self, event):
        was_dragging = self.drag_pos is not None
        self.drag_pos = None
        if was_dragging:
            self.anchor_to_ground()
        super().mouseReleaseEvent(event)

    # ---- Burbuja: texto y scroll ----

    def _bubble_set_text(self, text: str):
        self.bubble.setPlainText(text)
        self._bubble_scroll_bottom()

    def _bubble_scroll_bottom(self):
        bar = self.bubble.verticalScrollBar()
        bar.setValue(bar.maximum())

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
        self.bubble.setPlainText("🎤 Habla ahora..." if use_mic else "Pensando...")
        self._set_busy(True)
        self.anchor_to_ground()
        self.worker = AIWorker(
            self.ai, self.voice, prompt, use_mic, self.speech_enabled,
            history=list(self.history),
        )
        self.worker.status_update.connect(self.on_status_update)
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
        self.bubble.setPlainText("Consulta cancelada. Más rápida que tu paciencia, eh.")
        self.anchor_to_ground()

    def forget_conversation(self):
        self.history = []
        if self.worker is None and not self._closing:
            self.state = "IDLE"
            self.bubble.setPlainText("Memoria borrada. Como si nada hubiera pasado... justo como yo con tus preguntas raras.")

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
            self._bubble_set_text(status_text)

    def on_partial(self, text: str):
        if self._closing or self.worker is None:
            return
        self.bubble.setPlainText(text)
        self._bubble_scroll_bottom()

    def on_state_changed(self, state: str):
        if not self._closing:
            self.state = state

    def on_ai_response(self, response_text: str):
        if self._closing:
            return
        self._answer_received = True
        self._bubble_set_text(response_text)
        worker = self.worker
        if worker is not None:
            self.history.append({"role": "user", "content": worker.final_query})
            self.history.append({"role": "assistant", "content": response_text})
            if len(self.history) > 40:
                self.history = self.history[-40:]
        self.anchor_to_ground()

    def on_worker_error(self, message: str):
        if self._closing:
            return
        self._had_error = True
        self.state = "ERROR"
        if self._answer_received:
            self.bubble.appendPlainText("\n" + message)
            self._bubble_scroll_bottom()
        else:
            self._bubble_set_text(message)
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

    def closeEvent(self, event):
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
            self.bubble.setPlainText("Cerrando al terminar la operación en curso...")
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
            os._exit(0)
        self._save_settings()
        self.tray.hide()
        QApplication.instance().quit()

if __name__ == "__main__":
    lock = QLockFile(os.path.join(os.environ.get("TEMP", os.path.dirname(__file__)), "robot-asistente.lock"))
    if not lock.tryLock(100):
        # Ya hay un robot vivo: despertarlo y traerlo al frente en vez de morir en silencio.
        socket = QLocalSocket()
        socket.connectToServer(SINGLE_INSTANCE_NAME)
        if socket.waitForConnected(500):
            socket.write(b"show\n")
            socket.flush()
            socket.waitForBytesWritten(500)
            socket.disconnectFromServer()
        else:
            QMessageBox.warning(
                None,
                "Robot Asistente",
                "Robot Asistente ya está en ejecución.\n"
                "Búscalo en la bandeja del sistema (icono del robot).",
            )
        sys.exit(0)
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), "assets", "robot-assistant.ico")))
    app.setApplicationName("Robot Asistente")
    app.setOrganizationName("RobotAsistente")
    robot = DesktopRobot()
    robot.show()
    robot.start_single_instance_server()
    sys.exit(app.exec())
