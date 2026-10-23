"""Verificación visual: los ojos del robot deben delatar el estado por color."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from PyQt6.QtWidgets import QApplication

from unittest.mock import patch

with patch('dotenv.load_dotenv'):
    from ui import robot_window


ROBOT_H = 120
SPRITE_FACE = (100.8, 176.7, 316.6, 192.7)
SPRITE_SCALE_BASE = 512.0


def _eye_pixel(state, direction=1, edge=False):
    app = QApplication.instance() or QApplication([])
    with patch.object(robot_window, 'AIEngine'), patch.object(robot_window, 'VoiceEngine'):
        robot = robot_window.DesktopRobot()
    try:
        robot.anim_timer.stop()
        robot.show()
        robot.state = state
        robot.direction = direction
        robot.animation_tick = 8
        robot.is_blinking = False
        size = ROBOT_H * 0.96
        origin_x = robot.width() / 2 - size / 2
        origin_y = robot.height() - ROBOT_H + (ROBOT_H - size)
        scale = size / SPRITE_SCALE_BASE
        fx, fy, fw, fh = SPRITE_FACE
        look = 8 * direction if state == "MOVING" else 0
        offset = 26 if edge else 0
        cx = origin_x + (fx + fw * 0.261 + look + offset) * scale
        cy = origin_y + (fy + fh / 2) * scale
        image = robot.grab().toImage()
        return image.pixelColor(int(round(cx)), int(round(cy)))
    finally:
        robot.close()
        app.processEvents()


class VisualStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_sprite_is_loaded(self):
        with patch.object(robot_window, 'AIEngine'), patch.object(robot_window, 'VoiceEngine'):
            robot = robot_window.DesktopRobot()
        robot.close()
        self.assertIsNotNone(robot.robot_sprite, "El sprite 3D debería estar incluido en el repo")

    def _assert_close(self, pixel, rgb, tolerance=70):
        for component, expected in zip((pixel.red(), pixel.green(), pixel.blue()), rgb):
            self.assertLessEqual(abs(component - expected), tolerance)

    def test_idle_eyes_are_cyan(self):
        self._assert_close(_eye_pixel("IDLE"), (0, 240, 255))

    def test_listening_eyes_are_green(self):
        self._assert_close(_eye_pixel("LISTENING"), (0, 255, 140))

    def test_speaking_eyes_are_violet(self):
        self._assert_close(_eye_pixel("SPEAKING"), (170, 120, 255))

    def test_error_eyes_are_red(self):
        self._assert_close(_eye_pixel("ERROR"), (255, 75, 90), tolerance=90)

    def test_moving_eyes_follow_direction(self):
        # Muestreo en el borde derecho del ojo: mirando a la derecha el píxel
        # es cian (el ojo se ha movido hacia él); mirando a la izquierda, oscuro.
        right = _eye_pixel("MOVING", direction=1, edge=True)
        left = _eye_pixel("MOVING", direction=-1, edge=True)
        self.assertGreater(right.green(), 120)
        self.assertLess(left.green(), 100)


    def test_update_version_comparison(self):
        from core.updates import is_newer
        self.assertTrue(is_newer("2.1.0", "2.0.0"))
        self.assertFalse(is_newer("2.0.0", "2.0.0"))
        self.assertFalse(is_newer("1.9.9", "2.0.0"))


if __name__ == "__main__":
    unittest.main()
