import os
import threading
import time
import unittest
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

from PyQt6.QtCore import Qt, QPointF, QSettings, QTimer
from PyQt6.QtGui import QCloseEvent, QImage, QMouseEvent, QPixmap
from PyQt6.QtWidgets import QApplication

with patch('dotenv.load_dotenv'):
    import main
    from ui import robot_window


class FakeAI:
    def __init__(self):
        self.release = threading.Event()
        self.entered = threading.Event()
        self.calls = []
        self.images = []

    def ask(self, prompt, image=None):
        self.calls.append(prompt)
        self.images.append(image)
        self.entered.set()
        if not self.release.wait(3):
            raise TimeoutError('test deadline')
        return 'Respuesta conservada'


class FakeVoice:
    def __init__(self):
        self.release = threading.Event()
        self.entered = threading.Event()
        self.spoken = []
        self.error = False
        self.stopped = False

    def speak(self, text, should_stop=None):
        self.spoken.append(text)
        self.entered.set()
        if self.error:
            raise RuntimeError('audio disconnected')
        self.release.wait(3)

    def listen(self):
        return False, 'No se detectó voz'

    def stop(self):
        self.stopped = True
        self.release.set()


class RobotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        QSettings("RobotAsistente", "RobotAsistente").clear()
        self.ai = FakeAI()
        self.voice = FakeVoice()
        with patch.object(robot_window, 'AIEngine', return_value=self.ai), patch.object(
            robot_window, 'VoiceEngine', return_value=self.voice
        ):
            self.robot = robot_window.DesktopRobot()
        self.robot.anim_timer.stop()
        self.workers = []

    def tearDown(self):
        self.ai.release.set()
        self.voice.release.set()
        current = getattr(self.robot, 'worker', None)
        if current is not None and current not in self.workers:
            self.workers.append(current)
        for retired in list(getattr(self.robot, '_retired', [])):
            if retired not in self.workers:
                self.workers.append(retired)
        for worker in self.workers:
            try:
                worker.wait(4000)
            except RuntimeError:  # Qt may have already disposed a finished worker.
                pass
        self.app.processEvents()
        self.robot.close()
        self.app.processEvents()
        QSettings("RobotAsistente", "RobotAsistente").clear()

    def until(self, predicate):
        deadline = time.monotonic() + 2
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertTrue(predicate(), 'Qt condition did not complete')

    def send(self, text='Hola'):
        self.robot.text_input.setText(text)
        self.robot.send_text()
        worker = getattr(self.robot, 'worker', None)
        if worker is not None and worker not in self.workers:
            self.workers.append(worker)
        return worker

    def bubble_text(self):
        return self.robot.last_message_text()

    def test_second_send_and_mic_do_not_replace_active_worker(self):
        first = self.send()
        self.assertTrue(self.ai.entered.wait(1))
        second = self.send('Segunda')
        self.assertIs(second, first)
        self.robot.start_listening()
        self.assertIs(self.robot.worker, first)
        self.assertFalse(self.robot.text_input.isEnabled())
        self.assertFalse(self.robot.mic_btn.isEnabled())
        self.assertEqual(self.ai.calls, ['Hola'])

    def test_response_stays_visible_and_busy_until_voice_finishes(self):
        self.send()
        self.ai.release.set()
        self.until(self.voice.entered.is_set)
        self.until(lambda: self.bubble_text() == 'Respuesta conservada')
        self.assertEqual(self.robot.state, 'SPEAKING')
        self.assertFalse(self.robot.text_input.isEnabled())
        self.voice.release.set()
        self.until(lambda: getattr(self.robot, 'worker', None) is None)
        self.assertTrue(self.robot.text_input.isEnabled())
        self.assertEqual(self.robot.state, 'IDLE')

    def test_voice_failure_preserves_answer_and_reenables_input(self):
        self.voice.error = True
        self.ai.release.set()
        self.send()
        self.until(lambda: getattr(self.robot, 'worker', None) is None)
        self.assertIn('Respuesta conservada', self.bubble_text())
        self.assertTrue(self.robot.text_input.isEnabled())
        self.assertNotIn('audio disconnected', self.bubble_text())

    def test_close_waits_for_active_work_and_does_not_start_speech(self):
        worker = self.send()
        self.assertTrue(self.ai.entered.wait(1))
        event = QCloseEvent()
        self.robot.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertTrue(worker.isInterruptionRequested())
        self.assertTrue(self.voice.stopped)
        self.ai.release.set()
        self.until(lambda: getattr(self.robot, 'worker', None) is None)
        self.assertEqual(self.voice.spoken, [])

    def test_click_does_not_change_thinking_state(self):
        self.send()
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(155, self.robot.height() - 70), QPointF(155, 300),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.robot.mousePressEvent(event)
        self.assertEqual(self.robot.state, 'THINKING')

    def test_long_answer_remains_readable_inside_screen(self):
        self.robot.show()
        self.app.processEvents()
        answer = '<b>Texto plano</b> ' * 1000
        self.robot.on_ai_response(answer)
        self.app.processEvents()
        bounds = self.robot.screen().availableGeometry()
        self.assertGreaterEqual(self.robot.y(), bounds.top())
        self.assertLessEqual(self.robot.height(), bounds.height())
        self.assertEqual(self.bubble_text(), answer)
        self.assertGreater(self.robot.bubble.verticalScrollBar().maximum(), 0)

    def test_anchor_clamps_horizontal_position(self):
        self.robot.move(-10000, -10000)
        self.robot.anchor_to_ground()
        self.assertGreaterEqual(self.robot.x(), self.robot.screen().availableGeometry().left())

    def test_muting_during_request_skips_voice_and_preserves_answer(self):
        self.send()
        self.assertTrue(self.ai.entered.wait(1))
        self.robot.voice_btn.setChecked(False)
        self.ai.release.set()
        self.until(lambda: getattr(self.robot, 'worker', None) is None)
        self.assertEqual(self.voice.spoken, [])
        self.assertEqual(self.bubble_text(), 'Respuesta conservada')

    def test_muting_active_speech_requests_playback_stop(self):
        callbacks = []

        def speak(text, should_stop=None):
            callbacks.append(should_stop)
            self.voice.entered.set()
            self.voice.release.wait(3)

        self.voice.speak = speak
        self.ai.release.set()
        self.send()
        self.until(self.voice.entered.is_set)
        self.robot.voice_btn.setChecked(False)
        self.assertTrue(callbacks[0]())

    def test_hush_stops_speech_but_keeps_answer(self):
        self.send()
        self.assertTrue(self.ai.entered.wait(1))
        self.ai.release.set()
        self.until(self.voice.entered.is_set)
        self.until(lambda: self.robot.state == 'SPEAKING')
        self.robot.stop_clicked()
        self.until(lambda: getattr(self.robot, 'worker', None) is None)
        texts = [message['text'] for message in self.robot.chat_messages]
        self.assertIn('Respuesta conservada', texts)
        self.assertTrue(self.robot.text_input.isEnabled())
        self.assertTrue(self.voice.stopped)

    def test_history_accumulates_and_forget_clears_it(self):
        self.send()
        self.ai.release.set()
        self.voice.release.set()
        self.until(lambda: getattr(self.robot, 'worker', None) is None)
        self.assertEqual(self.robot.history[0], {'role': 'user', 'content': 'Hola'})
        self.assertEqual(self.robot.history[1], {'role': 'assistant', 'content': 'Respuesta conservada'})
        self.robot.forget_conversation()
        self.assertEqual(self.robot.history, [])

    def test_streaming_updates_bubble_and_history(self):
        def ask_stream(prompt, history=None, image=None):
            self.ai.entered.set()
            yield 'Hola '
            yield 'mundo'

        self.ai.ask_stream = ask_stream
        self.send()
        self.assertTrue(self.ai.entered.wait(1))
        self.until(lambda: self.bubble_text() == 'Hola mundo')
        self.ai.release.set()
        self.voice.release.set()
        self.until(lambda: getattr(self.robot, 'worker', None) is None)
        self.assertEqual(self.bubble_text(), 'Hola mundo')
        self.assertEqual(self.robot.history[1]['content'], 'Hola mundo')

    def test_cancel_unlocks_ui_and_drops_late_answer(self):
        worker = self.send()
        self.assertTrue(self.ai.entered.wait(1))
        self.robot.cancel_current()
        self.assertIsNone(self.robot.worker)
        self.assertTrue(worker.isInterruptionRequested())
        self.assertTrue(self.robot.text_input.isEnabled())
        self.assertTrue(self.robot.mic_btn.isEnabled())
        self.assertFalse(self.robot.stop_btn.isVisibleTo(self.robot))
        self.assertEqual(self.bubble_text(), 'Consulta cancelada. Más rápida que tu paciencia, eh.')
        self.ai.release.set()
        self.until(lambda: worker.isFinished())
        self.app.processEvents()
        self.assertEqual(self.bubble_text(), 'Consulta cancelada. Más rápida que tu paciencia, eh.')
        self.assertEqual(self.robot.history, [])

    def test_settings_persist_position_and_voice(self):
        settings = QSettings("RobotAsistente", "RobotAsistente")
        settings.setValue("window/x", 55)
        settings.setValue("voice/enabled", False)
        with patch.object(robot_window, 'AIEngine', return_value=self.ai), patch.object(
            robot_window, 'VoiceEngine', return_value=self.voice
        ):
            robot2 = robot_window.DesktopRobot()
        try:
            self.assertFalse(robot2.speech_enabled)
            self.assertFalse(robot2.voice_btn.isChecked())
            self.assertEqual(robot2.x(), 55)
        finally:
            robot2.close()
            settings.clear()

    def test_animation_uses_one_low_cost_timer(self):
        self.assertEqual(self.robot.anim_timer.interval(), 50)
        for timer in self.robot.findChildren(QTimer):
            self.assertGreaterEqual(timer.interval(), 50)

    def test_moving_tick_rebounds_at_both_edges(self):
        self.robot.show()
        for x, direction, expected_direction in (
            (self.robot.screen_left, -1, 1),
            (self.robot.screen_right, 1, -1),
        ):
            with self.subTest(x=x):
                self.robot.state = 'MOVING'
                self.robot.walk_pose = 'profile'
                self.robot._pose_ticks = 999
                self.robot.direction = direction
                self.robot.move(x, self.robot.screen_bottom - self.robot.height())
                self.robot.update_physics()
                self.assertEqual(self.robot.direction, expected_direction)
                self.assertGreaterEqual(self.robot.x(), self.robot.screen_left)
                self.assertLessEqual(self.robot.x(), self.robot.screen_right)

    def test_walking_pose_pauses_to_look_and_resumes(self):
        self.robot.show()
        self.robot.state = 'MOVING'
        self.robot.walk_pose = 'profile'
        self.robot._pose_ticks = 1
        self.robot.update_physics()
        self.assertEqual(self.robot.walk_pose, 'front')
        self.assertGreater(self.robot._pose_ticks, 0)
        # Al mirar de frente suelta una frase ácida sin machacar el chat.
        self.assertIn(self.robot._solo_text, self.robot.WALK_QUIPS)
        self.assertEqual(self.bubble_text(), self.robot._solo_text)
        ticks = self.robot._pose_ticks
        self.robot.update_physics()
        self.assertEqual(self.robot.walk_pose, 'front', 'debe seguir mirando de frente')
        self.robot._pose_ticks = 1
        self.robot.update_physics()
        self.assertEqual(self.robot.walk_pose, 'profile')
        self.assertGreater(self.robot._pose_ticks, 1)
        self.assertIsNone(self.robot._solo_text)

    def test_click_clears_quip_and_shows_conversation(self):
        self.robot.show()
        self.robot.state = 'MOVING'
        self.robot.walk_pose = 'front'
        self.robot._solo_text = 'Ni me hables. Tú a lo tuyo.'
        self.robot._toggle_controls()
        self.assertIsNone(self.robot._solo_text)
        self.assertEqual(self.robot.state, 'IDLE')

    def test_bubble_hidden_while_rolling_visible_when_front(self):
        self.robot.show()
        self.robot.state = 'MOVING'
        self.robot.walk_pose = 'profile'
        self.robot._pose_ticks = 999
        self.robot.update_physics()
        self.assertFalse(self.robot.bubble.isVisibleTo(self.robot))
        self.robot.walk_pose = 'front'
        self.robot.update_physics()
        self.assertTrue(self.robot.bubble.isVisibleTo(self.robot))
        self.robot.walk_pose = 'profile'
        self.robot.update_physics()
        self.assertFalse(self.robot.bubble.isVisibleTo(self.robot))
        self.robot._toggle_controls()  # controles abiertos -> de frente y con burbuja
        self.assertTrue(self.robot.bubble.isVisibleTo(self.robot))

    def test_walk_quip_is_spoken_aloud(self):
        spoken = []
        self.voice.speak = lambda text, should_stop=None: spoken.append(text)
        self.robot.show()
        self.robot.state = 'MOVING'
        self.robot.walk_pose = 'profile'
        self.robot._pose_ticks = 1
        self.robot.update_physics()
        deadline = time.monotonic() + 2
        while not spoken and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertEqual(spoken, [self.robot._solo_text])

    def test_walk_quip_silent_when_voice_muted(self):
        spoken = []
        self.voice.speak = lambda text, should_stop=None: spoken.append(text)
        self.robot.speech_enabled = False
        self.robot.show()
        self.robot.state = 'MOVING'
        self.robot.walk_pose = 'profile'
        self.robot._pose_ticks = 1
        self.robot.update_physics()
        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertEqual(spoken, [])
        self.assertIsNotNone(self.robot._solo_text, 'la frase se muestra aunque esté mudo')

    def test_vision_capture_reaches_the_ai_with_the_prompt(self):
        self.robot.show()
        pixmap = QPixmap(20, 20)
        pixmap.fill(Qt.GlobalColor.cyan)
        self.robot._on_region_captured(pixmap)
        pending = self.robot._pending_image
        self.assertTrue(pending and len(pending) > 100)
        self.robot.text_input.setText('¿Qué ves?')
        self.robot.send_text()
        self.assertTrue(self.ai.entered.wait(1))
        self.assertEqual(self.ai.images, [pending])
        self.assertEqual(self.ai.calls, ['¿Qué ves?'])
        self.ai.release.set()

    def test_streaming_speaks_sentences_as_they_arrive(self):
        def ask_stream(prompt, history=None, image=None):
            self.ai.entered.set()
            yield 'Hola. '
            yield '¿Qué tal? '
            yield 'Adiós.'

        spoken = []
        self.ai.ask_stream = ask_stream
        self.voice.speak = lambda text, should_stop=None: spoken.append(text)
        self.send()
        self.assertTrue(self.ai.entered.wait(1))
        deadline = time.monotonic() + 2
        while len(spoken) < 3 and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertEqual(spoken, ['Hola.', '¿Qué tal?', 'Adiós.'])
        self.ai.release.set()

    def test_extract_command_wake_words(self):
        from core.hands_free import extract_command
        self.assertEqual(extract_command('robot abre la calculadora'), 'abre la calculadora')
        self.assertEqual(extract_command('¡Oye robot, qué tal!'), 'qué tal')
        self.assertEqual(extract_command('Oye'), '')
        self.assertIsNone(extract_command('buenos días'))
        self.assertEqual(
            extract_command('robot qué tal', words=('robot',)),
            'qué tal',
        )

    def test_hands_free_toggle_starts_and_stops_loop(self):
        with patch.object(robot_window, 'HandsFreeLoop') as factory:
            loop = factory.return_value
            self.robot.show()
            self.robot.hands_free_action.setChecked(True)
            factory.assert_called_once_with(self.robot.voice)
            loop.start.assert_called_once()
            self.robot.hands_free_action.setChecked(False)
            loop.stop.assert_called_once()
            self.assertIsNone(self.robot.hands_free_loop)

    def test_hands_free_command_starts_worker(self):
        self.robot.show()
        self.robot._on_hands_free_command('abre la calculadora')
        self.assertTrue(self.ai.entered.wait(1))
        self.assertEqual(self.ai.calls, ['abre la calculadora'])
        self.ai.release.set()

    def test_side_sprite_is_loaded_and_mirrors_left(self):
        self.robot.show()
        self.robot.state = 'MOVING'
        self.robot.walk_pose = 'profile'
        if self.robot.robot_side is None:
            self.skipTest('sprite lateral no disponible')
        self.robot.direction = 1
        pixmap_right = self.robot._side_pixmap()
        self.robot.direction = -1
        pixmap_left = self.robot._side_pixmap()
        self.assertTrue(pixmap_left.toImage() != pixmap_right.toImage())

    def test_hiding_controls_resumes_profile_walk(self):
        self.robot.show()
        self.robot._toggle_controls()  # muestra controles -> de frente
        self.assertEqual(self.robot.state, 'IDLE')
        self.robot._toggle_controls()  # oculta controles -> paseo de perfil
        self.assertEqual(self.robot.state, 'MOVING')
        self.assertEqual(self.robot.walk_pose, 'profile')

    def test_error_has_a_visible_state_and_safe_reset(self):
        self.robot.on_worker_error('Fallo visible')
        self.assertEqual(self.robot.state, 'ERROR')
        self.robot.clear_error_state()
        self.assertEqual(self.robot.state, 'IDLE')
        self.robot.state = 'THINKING'
        self.robot.clear_error_state()
        self.assertEqual(self.robot.state, 'THINKING')

    def test_vector_visuals_render_for_every_state(self):
        for state in ('IDLE', 'MOVING', 'LISTENING', 'THINKING', 'SPEAKING', 'ERROR'):
            with self.subTest(state=state):
                self.robot.state = state
                image = QImage(
                    self.robot.size(),
                    QImage.Format.Format_ARGB32_Premultiplied,
                )
                image.fill(Qt.GlobalColor.transparent)
                self.robot.render(image)
                self.assertFalse(image.isNull())


if __name__ == '__main__':
    unittest.main()
