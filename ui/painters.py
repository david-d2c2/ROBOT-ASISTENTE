"""Pintado del robot: sprite 3D con ojos animados y respaldo vectorial SVG."""
import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QRadialGradient

from ui import theme

SPRITE_SCALE_BASE = 512.0


class RobotPaintingMixin:
    """Mixin de DesktopRobot: todo el render visual del personaje."""

    # ---- Dispatcher ----

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
        walking = (
            self.state == "MOVING"
            and self.drag_pos is None
            and not self.reduced_motion
        )
        if walking and self.walk_pose == "profile" and getattr(self, "robot_side", None) is not None:
            self._paint_side_robot(painter, phase)
            return
        self._paint_front_robot(painter, phase)

    def _paint_side_robot(self, painter, phase):
        """Rodando de perfil: sprite lateral, ruedas girando y bote de rodadura."""
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        size = self.ROBOT_DRAW_HEIGHT * 0.96
        bob = 0 if self._pose_switch > 0 else int(abs(math.sin(phase * 2)) * 2)
        origin_y = self.height() - self.ROBOT_DRAW_HEIGHT + (self.ROBOT_DRAW_HEIGHT - size)
        grow = 1.0
        if self._pose_switch > 0:
            grow = 1.0 - 0.85 * (self._pose_switch / 6.0)
        target_w = size * grow
        draw_x = self.width() / 2 - target_w / 2

        shadow_center_y = origin_y + size - 6
        shadow = QRadialGradient(QPointF(self.width() / 2, shadow_center_y), size * 0.48)
        shadow.setColorAt(0.0, QColor(0, 0, 0, 80))
        shadow.setColorAt(0.7, QColor(0, 0, 0, 40))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(shadow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            QPointF(self.width() / 2, shadow_center_y), size * 0.48, size * 0.11
        )

        pixmap = self._side_pixmap()
        painter.drawPixmap(
            QRectF(draw_x, origin_y + bob, target_w, size), pixmap, QRectF(pixmap.rect())
        )

        painter.save()
        painter.translate(draw_x, origin_y + bob)
        painter.scale(target_w / SPRITE_SCALE_BASE, size / SPRITE_SCALE_BASE)
        self._draw_side_wheels(painter)
        painter.restore()

    def _side_pixmap(self) -> QPixmap:
        if self.direction == -1:
            if self._side_mirrored is None:
                self._side_mirrored = QPixmap.fromImage(
                    self.robot_side.toImage().mirrored(True, False)
                )
            return self._side_mirrored
        return self.robot_side

    def _draw_side_wheels(self, painter):
        cx, cy, radius = self.SPRITE_SIDE_WHEEL
        if self.direction == -1:
            cx = SPRITE_SCALE_BASE - cx
        angle = math.radians(self.wheel_angle)
        painter.setPen(QPen(QColor(126, 145, 169), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for extra in (0.0, math.pi / 2):
            spoke = angle + extra
            dx = math.cos(spoke) * radius
            dy = math.sin(spoke) * radius
            painter.drawLine(QPointF(cx - dx, cy - dy), QPointF(cx + dx, cy + dy))

    def _paint_front_robot(self, painter, phase):
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
            center = QPointF(origin_x + (fx + fw / 2) * size / SPRITE_SCALE_BASE,
                             origin_y + bob + (fy + fh / 2) * size / SPRITE_SCALE_BASE)
            radius = size * (0.72 + (math.sin(phase * 2) + 1) * 0.05)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(theme.GREEN, 2.5))
            painter.drawEllipse(center, radius, radius)

        painter.drawPixmap(
            QRectF(origin_x, origin_y + bob, size, size),
            self.robot_sprite,
            QRectF(self.robot_sprite.rect()),
        )

        painter.save()
        painter.translate(origin_x, origin_y + bob)
        painter.scale(size / SPRITE_SCALE_BASE, size / SPRITE_SCALE_BASE)
        self._draw_sprite_antenna(painter)
        self._draw_sprite_face(painter, phase)
        painter.restore()

        if self.state == "SPEAKING":
            fx, fy, fw, fh = self.SPRITE_FACE
            self._draw_voice_bars(
                painter, origin_x + size + 8,
                origin_y + bob + (fy + fh / 2) * size / SPRITE_SCALE_BASE, 1.0, phase,
            )

    def _draw_sprite_antenna(self, painter):
        color = self._state_color()
        center = QPointF(*self.SPRITE_ANTENNA[:2])
        radius = self.SPRITE_ANTENNA[2]
        glow = QRadialGradient(center, radius * 1.9)
        glow.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 130))
        glow.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, radius * 1.9, radius * 1.9)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(center, radius, radius)

    def _draw_sprite_face(self, painter, phase):
        color = self._state_color()
        fx, fy, fw, fh = self.SPRITE_FACE
        center_y = fy + fh / 2
        look_x = 8 * self.direction if self.state == "MOVING" else (5 if self.hovered else 0)
        look_y = -5 if self.hovered else 0
        eye_cx_left = fx + fw * 0.261
        eye_cx_right = fx + fw * 0.739

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))

        if self.state == "ERROR":
            pen = QPen(color, 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for eye_cx in (eye_cx_left, eye_cx_right):
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
            for eye_cx, radius, direction in ((eye_cx_left, 26, 1), (eye_cx_right, 20, -1)):
                cy = center_y + direction * offset_y + look_y
                painter.drawEllipse(QPointF(eye_cx + look_x, cy), radius, radius)
                glint(eye_cx + look_x - radius / 3, cy - radius / 3)
        elif self.state == "LISTENING":
            radius = 24 + (math.sin(phase * 2) + 1) * 5
            for eye_cx in (eye_cx_left, eye_cx_right):
                painter.drawEllipse(QPointF(eye_cx + look_x, center_y + look_y), radius, radius)
                glint(eye_cx + look_x - radius / 3, center_y + look_y - radius / 3)
        elif self.state == "SPEAKING":
            height = 56 + (math.sin(phase * 3) + 1) * 16
            for eye_cx in (eye_cx_left, eye_cx_right):
                painter.drawRoundedRect(
                    QRectF(eye_cx + look_x - 21, center_y + look_y - height / 2, 42, height),
                    21, 21,
                )
                glint(eye_cx + look_x - 8, center_y + look_y - height / 4)
        else:
            if self.is_blinking:
                for eye_cx in (eye_cx_left, eye_cx_right):
                    painter.drawRoundedRect(
                        QRectF(eye_cx + look_x - 26, center_y + look_y - 5, 52, 10), 5, 5
                    )
            else:
                for eye_cx in (eye_cx_left, eye_cx_right):
                    painter.drawEllipse(QPointF(eye_cx + look_x, center_y + look_y), 29, 29)
                    glint(eye_cx + look_x - 9, center_y + look_y - 10)

    # ---- Robot vectorial de respaldo (si no existe el sprite 3D) ----

    def _paint_vector_robot(self, painter, phase):
        scale = self.ROBOT_DRAW_HEIGHT / self.ROBOT_VIEWBOX_H
        robot_w = self.ROBOT_VIEWBOX_W * scale
        origin_x = self.width() / 2 - robot_w / 2
        origin_y = self.height() - self.ROBOT_DRAW_HEIGHT
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

    def _state_color(self):
        return theme.state_color(self.state)

    def _body_bob(self, phase):
        if self.reduced_motion:
            return 0
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
