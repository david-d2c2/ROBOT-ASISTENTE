"""Pintado del robot: sprite 3D con ojos animados y respaldo vectorial SVG."""
import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap, QRadialGradient

from ui import theme

SPRITE_SCALE_BASE = 512.0


def look_towards(cx: float, cy: float, px: float, py: float, radio: float = 260.0):
    """Vector de mirada (-1..1) desde un centro hacia un punto: más cerca del
    centro, mirada más neutra; lejos, mirada plena en esa dirección."""
    dx, dy = px - cx, py - cy
    dist = math.hypot(dx, dy)
    if dist < 2:
        return 0.0, 0.0
    alcance = min(1.0, dist / radio)
    return dx / dist * alcance, dy / dist * alcance


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
        self._draw_sparks(painter)

    def _draw_sparks(self, painter):
        """Chispitas doradas con brillo, más tenues conforme se apagan."""
        for chispa in getattr(self, "_sparks", []):
            alfa = max(0, min(220, int(220 * chispa["life"] / chispa["vida"])))
            centro = QPointF(chispa["x"], chispa["y"])
            glow = QRadialGradient(centro, 6)
            glow.setColorAt(0.0, QColor(255, 205, 95, alfa))
            glow.setColorAt(1.0, QColor(255, 205, 95, 0))
            painter.setBrush(QBrush(glow))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(centro, 5, 5)

    # ---- Mirada y squash ----

    def _look_offsets(self, unidades: float = 9.0):
        """Los ojos miran al cursor; sin física corrida aún, comportamiento
        clásico (dirección de marcha o hover)."""
        cursor = getattr(self, "_cursor_local", None)
        if cursor is None:
            factor = unidades / 9.0
            if self.state == "MOVING":
                return 8 * self.direction * factor, 0.0
            return ((5 if self.hovered else 0) * factor, (-3 if self.hovered else 0) * factor)
        lx, ly = look_towards(
            self.width() / 2, self.height() - self.ROBOT_DRAW_HEIGHT * 0.55,
            cursor.x(), cursor.y(),
        )
        return lx * unidades, ly * unidades * 0.7

    def _squash_scale(self):
        """(sx, sy) del squash & stretch al aterrizar: se aplasta y recupera."""
        ticks = getattr(self, "_squash_ticks", 0)
        if ticks <= 0:
            return 1.0, 1.0
        amount = ticks / 8.0
        return 1.0 + 0.10 * amount, 1.0 - 0.16 * amount

    # ---- Robot 3D: render generado + ojos y antena animados por encima ----

    def _paint_sprite_robot(self, painter, phase):
        walking = (
            self.state == "MOVING"
            and self.drag_pos is None
            and not self.reduced_motion
        )
        leyendo = getattr(self, "_reading_ticks", 0) > 0
        if leyendo or not (walking and self.walk_pose == "profile" and getattr(self, "robot_side", None) is not None):
            self._paint_front_robot(painter, phase)
            if leyendo:
                self._draw_reading_tablet(
                    painter, phase, self.ROBOT_DRAW_HEIGHT * 0.96,
                    self.width() / 2, self.height() - self.ROBOT_DRAW_HEIGHT * 0.10,
                )
            return
        self._paint_side_robot(painter, phase)

    def _paint_side_robot(self, painter, phase):
        """Rodando de perfil: sprite lateral, ruedas girando y bote de rodadura."""
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        size = self.ROBOT_DRAW_HEIGHT * 0.96
        bob = 0 if self._pose_switch > 0 else int(abs(math.sin(phase * 2)) * 2)
        origin_y = self.height() - self.ROBOT_DRAW_HEIGHT + (self.ROBOT_DRAW_HEIGHT - size)
        grow = 1.0
        if self._pose_switch > 0:
            grow = 1.0 - 0.85 * (self._pose_switch / 6.0)
        sx, sy = self._squash_scale()
        target_w = size * grow * sx
        draw_h = size * sy
        draw_x = self.width() / 2 - target_w / 2
        draw_y = origin_y + bob + (size - draw_h)

        shadow_center_y = origin_y + size - 6
        shadow = QRadialGradient(QPointF(self.width() / 2, shadow_center_y), size * 0.48)
        shadow.setColorAt(0.0, QColor(0, 0, 0, 80))
        shadow.setColorAt(0.7, QColor(0, 0, 0, 40))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(shadow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            QPointF(self.width() / 2, shadow_center_y), size * 0.48 * sx, size * 0.11
        )

        pixmap = self._side_pixmap()
        painter.drawPixmap(
            QRectF(draw_x, draw_y, target_w, draw_h), pixmap, QRectF(pixmap.rect())
        )

        painter.save()
        painter.translate(draw_x, draw_y)
        painter.scale(target_w / SPRITE_SCALE_BASE, draw_h / SPRITE_SCALE_BASE)
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
        sx, sy = self._squash_scale()
        draw_w, draw_h = size * sx, size * sy
        draw_x = origin_x - (draw_w - size) / 2
        draw_y = origin_y + bob + (size - draw_h)

        shadow_center_y = origin_y + size - 6
        shadow = QRadialGradient(QPointF(origin_x + size / 2, shadow_center_y), size * 0.48)
        shadow.setColorAt(0.0, QColor(0, 0, 0, 80))
        shadow.setColorAt(0.7, QColor(0, 0, 0, 40))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(shadow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            QPointF(origin_x + size / 2, shadow_center_y), size * 0.48 * sx, size * 0.11
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
            QRectF(draw_x, draw_y, draw_w, draw_h),
            self.robot_sprite,
            QRectF(self.robot_sprite.rect()),
        )

        painter.save()
        painter.translate(draw_x, draw_y)
        painter.scale(draw_w / SPRITE_SCALE_BASE, draw_h / SPRITE_SCALE_BASE)
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
        look_x, look_y = self._look_offsets()
        if getattr(self, "_reading_ticks", 0) > 0:
            look_x, look_y = 0.0, 9.0  # leyendo: la vista baja al periódico
        mood = getattr(self, "mood", None)
        eye_cx_left = fx + fw * 0.261
        eye_cx_right = fx + fw * 0.739
        mouth_y = fy + fh * 0.80

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

        def smile(cx, width=54, pen_width=9):
            painter.save()
            painter.setPen(QPen(color, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(QRectF(cx - width / 2, mouth_y - width * 0.3, width, width * 0.55),
                            180 * 16, 180 * 16)
            painter.restore()
            painter.setBrush(QBrush(color))

        def mouth_open(cx, ry, rx=21.0):
            painter.drawEllipse(QPointF(cx + look_x * 0.35, mouth_y + look_y * 0.25), rx, ry)

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
            if mood == "happy":
                smile(fx + fw / 2 + look_x * 0.35)
            else:
                # La boca se abre y cierra con la onda de la voz.
                mouth_open(fx + fw / 2, 7 + (math.sin(phase * 4) + 1) * 8)
        else:
            if mood == "happy":
                for eye_cx in (eye_cx_left, eye_cx_right):
                    painter.drawEllipse(QPointF(eye_cx + look_x, center_y + look_y), 29, 29)
                    glint(eye_cx + look_x - 9, center_y + look_y - 10)
                smile(fx + fw / 2 + look_x * 0.35)
            elif mood == "surprised":
                for eye_cx in (eye_cx_left, eye_cx_right):
                    painter.drawEllipse(QPointF(eye_cx + look_x, center_y + look_y), 33, 33)
                    glint(eye_cx + look_x - 10, center_y + look_y - 12)
                mouth_open(fx + fw / 2, 13, rx=13)
            elif mood == "confused":
                painter.drawEllipse(QPointF(eye_cx_left + look_x, center_y + look_y), 29, 29)
                glint(eye_cx_left + look_x - 9, center_y + look_y - 10)
                painter.drawRoundedRect(
                    QRectF(eye_cx_right + look_x - 22, center_y + look_y - 7, 44, 13), 6, 6
                )
                painter.save()
                painter.setPen(QPen(color, 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(
                    QPointF(fx + fw / 2 - 13 + look_x, mouth_y + 5),
                    QPointF(fx + fw / 2 + 13 + look_x, mouth_y - 5),
                )
                painter.restore()
            elif mood == "sleepy":
                # Ojos caídos a media asta y zZ flotando junto a la antena.
                for eye_cx in (eye_cx_left, eye_cx_right):
                    painter.drawRoundedRect(
                        QRectF(eye_cx + look_x - 26, center_y + 8 + look_y, 52, 13), 6, 6
                    )
                ax, ay, _radio = self.SPRITE_ANTENNA
                painter.save()
                painter.setPen(QPen(color, 5))
                floateo = math.sin(phase * 1.5) * 4
                painter.setFont(QFont("Arial", 30))
                painter.drawText(QPointF(ax + 34, ay + 10 + floateo), "z")
                painter.setFont(QFont("Arial", 22))
                painter.drawText(QPointF(ax + 64, ay - 18 - floateo), "Z")
                painter.restore()
                painter.setPen(Qt.PenStyle.NoPen)
            elif self.is_blinking:
                for eye_cx in (eye_cx_left, eye_cx_right):
                    painter.drawRoundedRect(
                        QRectF(eye_cx + look_x - 26, center_y + look_y - 5, 52, 10), 5, 5
                    )
            else:
                for eye_cx in (eye_cx_left, eye_cx_right):
                    painter.drawEllipse(QPointF(eye_cx + look_x, center_y + look_y), 29, 29)
                    glint(eye_cx + look_x - 9, center_y + look_y - 10)

    def _draw_reading_tablet(self, painter, phase, ancho_robot, centro_x, suelo_y):
        """Periódico holográfico: el robot se para a leer las noticias."""
        color = theme.accent()
        flotar = math.sin(phase * 1.2) * 2
        ancho, alto = ancho_robot * 0.58, ancho_robot * 0.27
        rect = QRectF(centro_x - ancho / 2, suelo_y - alto * 1.55 + flotar, ancho, alto)

        glow = QRadialGradient(rect.center(), ancho * 0.75)
        glow.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 60))
        glow.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(rect.center(), ancho * 0.75, alto)

        painter.setBrush(QColor(8, 16, 30, 216))
        painter.setPen(QPen(color, 2))
        painter.drawRoundedRect(rect, 8, 8)

        margen = ancho * 0.07
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.setFont(QFont("Segoe UI Emoji", max(8, int(alto * 0.34))))
        painter.drawText(QRectF(rect.left() + margen, rect.top() + alto * 0.10,
                                ancho * 0.45, alto * 0.34), Qt.AlignmentFlag.AlignLeft, "📰")
        suave = QColor(color.red(), color.green(), color.blue(), 130)
        painter.setBrush(QBrush(suave))
        for fraccion in (0.48, 0.63, 0.78):
            painter.drawRect(QRectF(rect.left() + margen, rect.top() + alto * fraccion,
                                    ancho - 2 * margen, alto * 0.07))

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

        if getattr(self, "_reading_ticks", 0) > 0:
            painter.save()
            painter.translate(origin_x, origin_y + bob)
            painter.scale(scale, scale)
            self._draw_reading_tablet(
                painter, phase, self.ROBOT_VIEWBOX_W, self.ROBOT_VIEWBOX_W / 2,
                self.ROBOT_VIEWBOX_H * 0.9,
            )
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
        look_x, look_y = self._look_offsets(unidades=4.0)
        if getattr(self, "_reading_ticks", 0) > 0:
            look_x, look_y = 0.0, 4.0  # leyendo: la vista baja al periódico
        mood = getattr(self, "mood", None)

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

        def smile():
            painter.save()
            painter.setPen(QPen(color, 3.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(QRectF(86, 88, 28, 15), 180 * 16, 180 * 16)
            painter.restore()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))

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
            if mood == "happy":
                smile()
            else:
                boca_h = 4 + (math.sin(phase * 4) + 1) * 3.5
                painter.drawEllipse(QPointF(100 + look_x * 0.4, 95), 8, boca_h)
        elif mood == "happy":
            for eye_cx in (69.5, 113.5):
                painter.drawRoundedRect(QRectF(eye_cx + look_x, 60.5 + look_y, 17, 25), 8.5, 8.5)
                self._eye_glint(painter, eye_cx + 4 + look_x, 67.5 + look_y)
            smile()
        elif mood == "sleepy":
            for eye_cx in (69.5, 113.5):
                painter.drawRoundedRect(QRectF(eye_cx + look_x, 72 + look_y, 17, 7), 3.5, 3.5)
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
