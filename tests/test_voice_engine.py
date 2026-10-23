import asyncio
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from core.voice_engine import VoiceEngine


class VoiceEngineTests(unittest.TestCase):
    def setUp(self):
        self.mixer_patch = patch('core.voice_engine.pygame.mixer')
        self.mixer = self.mixer_patch.start()
        self.addCleanup(self.mixer_patch.stop)
        self.mixer.get_init.return_value = None
        self.mixer.music.get_busy.return_value = False
        self.directory = tempfile.TemporaryDirectory(dir=os.path.dirname(__file__))
        self.addCleanup(self.directory.cleanup)
        original_temp = tempfile.NamedTemporaryFile
        temp_patch = patch('core.voice_engine.tempfile.NamedTemporaryFile',
                           side_effect=lambda **kw: original_temp(dir=self.directory.name, **kw))
        temp_patch.start()
        self.addCleanup(temp_patch.stop)
        self.save_patch = patch('core.voice_engine.edge_tts.Communicate')
        self.communicate = self.save_patch.start()
        self.addCleanup(self.save_patch.stop)
        self.communicate.return_value.save = AsyncMock()

    def test_constructor_works_without_sound_device(self):
        self.mixer.init.side_effect = OSError('no device')
        try:
            VoiceEngine()
        except OSError:
            self.fail('Constructor must not open an audio device')
        self.mixer.init.assert_not_called()

    def test_speech_cleans_text_and_removes_file(self):
        VoiceEngine().speak('**Hola**   _amiga_')
        self.assertEqual(self.communicate.call_args.args[0], 'Hola amiga')
        self.mixer.music.play.assert_called_once()
        self.mixer.music.unload.assert_called_once()
        self.assertEqual(os.listdir(self.directory.name), [])

    def test_output_failure_is_friendly(self):
        engine = VoiceEngine()
        self.mixer.init.side_effect = OSError('no device')
        with self.assertRaisesRegex(RuntimeError, 'audio'):
            engine.speak('Hola')
        self.assertEqual(os.listdir(self.directory.name), [])

    def test_generation_failure_is_friendly_and_removes_file(self):
        self.communicate.return_value.save.side_effect = OSError('offline')
        with self.assertRaisesRegex(RuntimeError, 'voz'):
            VoiceEngine().speak('Hola')
        self.assertEqual(os.listdir(self.directory.name), [])

    def test_generation_is_bounded_and_cancelled(self):
        cancelled = []
        async def hang(_):
            try:
                await asyncio.sleep(0.03)
            finally:
                cancelled.append(True)
        self.communicate.return_value.save.side_effect = hang
        real_wait_for = asyncio.wait_for
        async def fast_wait_for(awaitable, timeout):
            self.assertEqual(timeout, 30)
            return await real_wait_for(awaitable, timeout=0.01)
        with patch('core.voice_engine.asyncio.wait_for', side_effect=fast_wait_for):
            with self.assertRaisesRegex(RuntimeError, 'voz'):
                VoiceEngine().speak('Hola')
        self.assertEqual(cancelled, [True])
        self.assertEqual(os.listdir(self.directory.name), [])

    def test_playback_errors_still_unload_and_remove_file(self):
        for method in ('load', 'play'):
            with self.subTest(method=method):
                self.mixer.music.reset_mock(side_effect=True)
                getattr(self.mixer.music, method).side_effect = OSError('broken playback')
                with self.assertRaisesRegex(RuntimeError, 'audio'):
                    VoiceEngine().speak('Hola')
                self.mixer.music.unload.assert_called_once()
                self.assertEqual(os.listdir(self.directory.name), [])

    def test_callback_cancels_before_generation(self):
        VoiceEngine().speak('Hola', should_stop=lambda: True)
        self.communicate.assert_not_called()

    def test_cleanup_error_is_friendly_and_removes_file(self):
        self.mixer.music.unload.side_effect = OSError('unload failed')
        with self.assertRaisesRegex(RuntimeError, 'audio'):
            VoiceEngine().speak('Hola')
        self.assertEqual(os.listdir(self.directory.name), [])

    def test_stop_during_generation_skips_playback(self):
        engine = VoiceEngine()
        self.assertTrue(hasattr(engine, 'stop'), 'VoiceEngine needs stop()')
        async def stop(_):
            engine.stop()
        self.communicate.return_value.save.side_effect = stop
        engine.speak('Hola')
        self.mixer.music.play.assert_not_called()
        self.assertEqual(os.listdir(self.directory.name), [])

    def test_stop_during_playback_cleans_up(self):
        engine = VoiceEngine()
        self.assertTrue(hasattr(engine, 'stop'), 'VoiceEngine needs stop()')
        def busy():
            engine.stop()
            return True
        self.mixer.music.get_busy.side_effect = busy
        engine.speak('Hola')
        self.mixer.music.stop.assert_called()
        self.mixer.music.unload.assert_called_once()
        self.assertEqual(os.listdir(self.directory.name), [])

    def test_recognition_uses_https_and_bounded_io(self):
        with patch('core.voice_engine.sr.Recognizer') as factory, patch('core.voice_engine.sr.Microphone'):
            recognizer = factory.return_value
            recognizer.recognize_google.return_value = 'hola'
            self.assertEqual(VoiceEngine().listen(), (True, 'hola'))
            self.assertEqual(recognizer.operation_timeout, 15)
            self.assertEqual(recognizer.listen.call_args.kwargs, {'timeout': 6, 'phrase_time_limit': 12})
            self.assertEqual(recognizer.recognize_google.call_args.kwargs['endpoint'],
                             'https://www.google.com/speech-api/v2/recognize')

    def test_recognition_errors_do_not_expose_internal_details(self):
        secret = r'C:\Users\persona\audio\token-secreto'
        for error, expected in (
            (OSError(secret), 'micrófono'),
            (RuntimeError(secret), 'procesar voz'),
        ):
            with self.subTest(error=type(error).__name__):
                with patch('core.voice_engine.sr.Microphone', side_effect=error):
                    success, message = VoiceEngine().listen()
                self.assertFalse(success)
                self.assertIn(expected, message)
                self.assertNotIn(secret, message)

    def test_tts_is_configurable_via_environment(self):
        with patch.dict(os.environ, {
            'TTS_VOICE': 'es-MX-DaliaNeural',
            'TTS_RATE': '+20%',
            'TTS_PITCH': '+5Hz',
        }):
            VoiceEngine().speak('Hola')
        self.assertEqual(self.communicate.call_args.args, ('Hola', 'es-MX-DaliaNeural'))
        self.assertEqual(self.communicate.call_args.kwargs['rate'], '+20%')
        self.assertEqual(self.communicate.call_args.kwargs['pitch'], '+5Hz')

    def test_stop_is_reset_by_the_next_listen(self):
        with patch('core.voice_engine.sr.Recognizer') as factory, patch('core.voice_engine.sr.Microphone'):
            engine = VoiceEngine()
            engine.stop()
            factory.return_value.recognize_google.return_value = 'hola'
            success, text = engine.listen()
            self.assertTrue(success)
            self.assertEqual(text, 'hola')

    def test_empty_transcription_is_reported_as_unintelligible(self):
        with patch('core.voice_engine.sr.Recognizer') as factory, patch('core.voice_engine.sr.Microphone'):
            factory.return_value.recognize_google.return_value = '   '
            success, message = VoiceEngine().listen()
        self.assertFalse(success)
        self.assertIn('no entendí', message)

    def test_whisper_provider_transcribes_locally(self):
        fake_module = Mock()
        segments = iter([SimpleNamespace(text='Hola '), SimpleNamespace(text='mundo')])
        fake_module.WhisperModel.return_value.transcribe.return_value = (segments, None)
        with patch.dict(os.environ, {'STT_PROVIDER': 'whisper', 'STT_LANGUAGE': 'es-ES'}):
            with patch.dict(sys.modules, {'faster_whisper': fake_module}):
                with patch('core.voice_engine.sr.Recognizer') as factory, patch('core.voice_engine.sr.Microphone'):
                    audio = Mock()
                    audio.get_wav_data.return_value = b'\x00\x00' * 64
                    factory.return_value.listen.return_value = audio
                    success, text = VoiceEngine().listen()
        self.assertTrue(success)
        self.assertEqual(text, 'Hola mundo')
        kwargs = fake_module.WhisperModel.call_args.kwargs
        self.assertEqual(kwargs['device'], 'auto')
        self.assertEqual(kwargs['compute_type'], 'int8')
        self.assertEqual(fake_module.WhisperModel.call_args.args[0], 'base')
        transcribe_kwargs = fake_module.WhisperModel.return_value.transcribe.call_args.kwargs
        self.assertEqual(transcribe_kwargs['language'], 'es')

    def test_whisper_missing_dependency_is_friendly(self):
        with patch.dict(os.environ, {'STT_PROVIDER': 'whisper'}):
            with patch.dict(sys.modules, {'faster_whisper': None}):
                with patch('core.voice_engine.sr.Recognizer') as factory, patch('core.voice_engine.sr.Microphone'):
                    audio = Mock()
                    audio.get_wav_data.return_value = b''
                    factory.return_value.listen.return_value = audio
                    success, message = VoiceEngine().listen()
        self.assertFalse(success)
        self.assertIn('requirements-whisper', message)


if __name__ == '__main__':
    unittest.main()
