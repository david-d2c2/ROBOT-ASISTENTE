"""Vida del robot: mirada, emociones, noche, easing y aterrizaje físico."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from PyQt6.QtCore import QPoint, QPointF
from PyQt6.QtWidgets import QApplication
from unittest.mock import patch

with patch('dotenv.load_dotenv'):
    from ui import robot_window
from ui.painters import look_towards


class FakeAI:
    def ask_stream(self, *a, **k):
        return iter(())


class FakeVoice:
    def speak(self, text, should_stop=None):
        pass

    def stop(self):
        pass


def _robot():
    with patch.object(robot_window, 'AIEngine'), patch.object(robot_window, 'VoiceEngine'):
        robot = robot_window.DesktopRobot()
    robot.anim_timer.stop()
    robot.scheduler.stop()
    robot.news_agent.shutdown()
    return robot


class LookTests(unittest.TestCase):
    def test_look_towards_direction_and_reach(self):
        # Lejos del radio de confort: mirada plena hacia el lado correcto.
        lx, ly = look_towards(100, 100, 500, 100)
        self.assertAlmostEqual(lx, 1.0, places=5)
        self.assertAlmostEqual(ly, 0.0, places=5)
        lx, ly = look_towards(100, 100, 100, 50)
        self.assertAlmostEqual(lx, 0.0, places=5)
        self.assertLess(ly, 0)  # en pantalla, hacia arriba es negativo
        # Cerca del centro: mirada casi neutra.
        lx, ly = look_towards(100, 100, 108, 100)
        self.assertLess(lx, 0.2)
        # Encima del centro: neutra exacta.
        self.assertEqual(look_towards(0, 0, 1, 0), (0.0, 0.0))

    def test_eyes_follow_cursor_when_physics_ran(self):
        app = QApplication.instance() or QApplication([])
        robot = _robot()
        try:
            robot.show()
            robot.state = "IDLE"
            centro_x, centro_y = robot.width() / 2, robot.height() - robot.ROBOT_DRAW_HEIGHT * 0.55
            robot._cursor_local = QPointF(centro_x + 400, centro_y)  # cursor muy a la derecha
            lx, _ = robot._look_offsets()
            self.assertGreater(lx, 5)
        finally:
            robot.close()
            app.processEvents()

    def test_without_physics_the_classic_look_stays(self):
        app = QApplication.instance() or QApplication([])
        robot = _robot()
        try:
            robot.show()
            robot._cursor_local = None
            robot.state = "MOVING"
            robot.direction = -1
            lx, ly = robot._look_offsets()
            self.assertEqual(lx, -8)
            self.assertEqual(ly, 0.0)
        finally:
            robot.close()
            app.processEvents()


class SquashTests(unittest.TestCase):
    def test_squash_scales_and_recovers(self):
        app = QApplication.instance() or QApplication([])
        robot = _robot()
        try:
            robot._squash_ticks = 0
            self.assertEqual(robot._squash_scale(), (1.0, 1.0))
            robot._squash_ticks = 8  # recién suelta
            sx, sy = robot._squash_scale()
            self.assertGreater(sx, 1.0)   # se ensancha
            self.assertLess(sy, 1.0)      # se aplasta
            robot._squash_ticks = 1       # casi recuperado
            sx2, sy2 = robot._squash_scale()
            self.assertLess(sx2, sx)
            self.assertGreater(sy2, sy)
        finally:
            robot.close()
            app.processEvents()


class MoodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.robot = _robot()
        self.addCleanup(self.robot.close)

    def test_mood_expires_with_its_ticks(self):
        self.robot.set_mood("happy", ticks=3)
        self.assertEqual(self.robot.mood, "happy")
        for _ in range(3):
            self.robot._mood_step()
        self.assertIsNone(self.robot.mood)

    def test_sleepy_arrives_when_idle_too_long_and_wakes_on_activity(self):
        self.robot.worker = None
        self.robot._night = False
        self.robot._last_activity -= 400  # llevas un rato sin tocarle
        self.robot._mood_step()
        self.assertEqual(self.robot.mood, "sleepy")
        self.robot._touch_activity()
        self.assertIsNone(self.robot.mood)

    def test_sleepy_persists_at_night_until_morning_activity(self):
        self.robot.worker = None
        self.robot._night = True
        self.robot._mood_step()
        self.assertEqual(self.robot.mood, "sleepy")

    def test_night_mode_reading(self):
        with patch.object(robot_window.app_settings, "env", return_value="1"):
            self.robot._night_recheck = 0
            self.robot._night_step()
        self.assertTrue(self.robot._night)
        with patch.object(robot_window.app_settings, "env", return_value="0"):
            self.robot._night_recheck = 0
            self.robot._night_step()
        self.assertFalse(self.robot._night)

    def test_night_slows_the_walk(self):
        self.robot.show()
        self.robot.state = "MOVING"
        self.robot.walk_pose = "profile"

        def velocidad_estable(noche: bool) -> float:
            # NIGHT_MODE fijado: la reevaluación por reloj no pisa el test.
            with patch.object(robot_window.app_settings, "env",
                              return_value="1" if noche else "0"):
                self.robot._night_recheck = 0
                self.robot._night_step()
                self.robot._current_speed = 0.0
                for _ in range(40):  # deja que el easing converja
                    self.robot._pose_ticks = 999
                    self.robot.update_physics()
            return self.robot._current_speed

        noche = velocidad_estable(True)
        dia = velocidad_estable(False)
        self.assertGreater(dia, self.robot.speed * 0.9)
        self.assertLess(noche, dia * 0.75)


class MovementFeelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.robot = _robot()
        self.addCleanup(self.robot.close)

    def test_walk_accelerates_smoothly(self):
        self.robot.show()
        self.robot.state = "MOVING"
        self.robot.walk_pose = "profile"
        self.robot._pose_ticks = 999
        self.robot._current_speed = 0.0
        self.robot.update_physics()
        self.assertGreater(self.robot._current_speed, 0.0)
        self.assertLess(self.robot._current_speed, self.robot.speed)  # aún no al máximo

    def test_release_with_velocity_slides_and_lands(self):
        self.robot.show()
        # En medio de la pantalla: la derrapada no debe chocar con el borde.
        self.robot.move((self.robot.screen_left + self.robot.screen_right) // 2,
                        self.robot.screen_bottom - self.robot.height())
        self.robot._slide_velocity = 10.0
        self.robot._slide_ticks = 8
        self.robot._squash_ticks = 0
        inicio = self.robot.x()
        self.robot._slide_step()
        self.assertEqual(self.robot._squash_ticks, 0)   # derrapando: aún sin aplastar
        self.assertNotEqual(self.robot.x(), inicio)     # derrapa un poco
        while self.robot._slide_ticks > 0:
            self.robot._slide_step()
        self.assertEqual(self.robot._squash_ticks, 8)   # al parar, aterriza con squash
        # La física normal no mueve mientras dura la derrapada.
        self.robot._slide_ticks = 3
        self.robot.state = "MOVING"
        self.robot.walk_pose = "profile"
        self.robot._pose_ticks = 999
        durante = self.robot.x()
        self.robot.update_physics()
        self.assertEqual(self.robot.x(), durante)

    def test_drag_moves_the_window(self):
        """Regresión: el arrastre se perdió en el refactor de la 3.0."""
        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import QEvent, Qt, QPointF as QPF
        self.robot.show()
        inicio = self.robot.x()
        # drag_pos = cursor global − esquina de la ventana; lo ponemos en (170, 300).
        self.robot.drag_pos = QPoint(170, 300)
        self.robot._last_drag_x = inicio
        objetivo_global = QPF(inicio + 170 + 250, 600)  # suelta el ratón 250 px a la derecha
        evento = QMouseEvent(
            QEvent.Type.MouseMove, objetivo_global, objetivo_global, objetivo_global,
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.robot.mouseMoveEvent(evento)
        self.assertGreater(self.robot.x(), inicio)                    # la ventana siguió al cursor
        self.assertGreaterEqual(self.robot._slide_velocity, 14.0 - 0.1)  # velocidad para la inercia
        self.robot.mouseReleaseEvent(_release_event(self.robot))
        self.assertGreater(self.robot._slide_ticks, 0)                # hay derrape al soltar
        self.assertEqual(self.robot._squash_ticks, 8)


def _release_event(robot):
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent, Qt, QPointF as QPF
    punto = QPF(robot.x() + 170, 600)
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease, punto, punto, punto,
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


if __name__ == "__main__":
    unittest.main()
