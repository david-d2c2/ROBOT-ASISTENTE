import importlib
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

with patch('dotenv.load_dotenv'):
    from core import ai_engine


class AIEngineTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.gemini = patch('core.ai_engine.genai.Client').start()
        self.openai = patch('openai.OpenAI').start()
        self.post = patch('core.ai_engine.requests.post').start()
        self.addCleanup(patch.stopall)

    def test_constructor_defers_client_initialization(self):
        for provider in ('gemini', 'openai'):
            with self.subTest(provider=provider):
                os.environ.update(AI_PROVIDER=provider, GEMINI_API_KEY='test', OPENAI_API_KEY='test', GEMINI_MODEL='invalid')
                ai_engine.AIEngine()
        self.gemini.assert_not_called()
        self.openai.assert_not_called()

    def test_configuration_errors_raise_instead_of_becoming_answers(self):
        for provider, message in [('gemini', 'GEMINI_API_KEY'), ('openai', 'OPENAI_API_KEY'), ('unknown', 'proveedor')]:
            with self.subTest(provider=provider):
                os.environ['AI_PROVIDER'] = provider
                with self.assertRaisesRegex(RuntimeError, message):
                    ai_engine.AIEngine().ask('Hola')

    def test_gemini_preserves_model_and_bounds_requests(self):
        os.environ.update(GEMINI_API_KEY='test', GEMINI_MODEL='my-configured-model')
        self.gemini.return_value.models.generate_content.return_value = SimpleNamespace(text=' **Hola** ')
        self.assertEqual(ai_engine.AIEngine().ask('Hola'), 'Hola')
        options = self.gemini.call_args.kwargs['http_options']
        self.assertEqual(options.timeout, 30000)
        self.assertEqual(options.retry_options.attempts, 1)
        self.assertEqual(self.gemini.return_value.models.generate_content.call_args.kwargs['model'], 'my-configured-model')

    def test_openai_bounds_requests(self):
        os.environ.update(
            AI_PROVIDER='openai',
            OPENAI_API_KEY='test',
            OPENAI_MODEL='my-openai-model',
        )
        self.openai.return_value.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='Hola'))])
        self.assertEqual(ai_engine.AIEngine().ask('Hola'), 'Hola')
        self.assertEqual(self.openai.call_args.kwargs['timeout'], 30)
        self.assertEqual(self.openai.call_args.kwargs['max_retries'], 0)
        self.assertEqual(
            self.openai.return_value.chat.completions.create.call_args.kwargs['model'],
            'my-openai-model',
        )

    def test_zai_requires_api_key(self):
        os.environ['AI_PROVIDER'] = 'zai'
        with self.assertRaisesRegex(RuntimeError, 'ZAI_API_KEY'):
            ai_engine.AIEngine().ask('Hola')

    def test_zai_uses_openai_compatible_client_and_model(self):
        os.environ.update(
            AI_PROVIDER='zai',
            ZAI_API_KEY='test',
            ZAI_MODEL='glm-4.6',
        )
        self.openai.return_value.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='Hola'))])
        self.assertEqual(ai_engine.AIEngine().ask('Hola'), 'Hola')
        kwargs = self.openai.call_args.kwargs
        self.assertEqual(kwargs['base_url'], 'https://api.z.ai/api/paas/v4/')
        self.assertEqual(kwargs['timeout'], 30)
        self.assertEqual(kwargs['max_retries'], 0)
        self.assertEqual(
            self.openai.return_value.chat.completions.create.call_args.kwargs['model'],
            'glm-4.6',
        )

    def test_history_is_forwarded_to_chat_messages(self):
        os.environ.update(AI_PROVIDER='openai', OPENAI_API_KEY='test')
        history = [
            {'role': 'user', 'content': 'Hola'},
            {'role': 'assistant', 'content': '¡Bip!'},
            {'role': 'assistant', 'content': ''},  # se ignora
        ]
        self.openai.return_value.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='Bien'))])
        ai_engine.AIEngine().ask('¿Todo bien?', history=history)
        messages = self.openai.return_value.chat.completions.create.call_args.kwargs['messages']
        self.assertEqual(
            messages,
            [
                {'role': 'system', 'content': ai_engine.SYSTEM_PROMPT},
                {'role': 'user', 'content': 'Hola'},
                {'role': 'assistant', 'content': '¡Bip!'},
                {'role': 'user', 'content': '¿Todo bien?'},
            ],
        )

    def test_history_is_bounded_by_configured_turns(self):
        os.environ.update(AI_PROVIDER='openai', OPENAI_API_KEY='test', CHAT_HISTORY_TURNS='1')
        history = [{'role': 'user', 'content': f'm{i}'} for i in range(6)]
        self.openai.return_value.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='Bien'))])
        ai_engine.AIEngine().ask('Hola', history=history)
        messages = self.openai.return_value.chat.completions.create.call_args.kwargs['messages']
        self.assertEqual(len(messages), 4)  # system + 2 entradas (1 turno) + pregunta
        self.assertEqual(messages[1]['content'], 'm4')

    def test_streaming_yields_cleaned_chunks(self):
        os.environ.update(AI_PROVIDER='openai', OPENAI_API_KEY='test')
        chunks = [
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='*Ho'))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='la*'))]),
        ]
        self.openai.return_value.chat.completions.create.return_value = iter(chunks)
        out = ''.join(ai_engine.AIEngine().ask_stream('Hola'))
        self.assertEqual(out, 'Hola')

    def test_streaming_raises_safe_error_on_empty(self):
        os.environ.update(AI_PROVIDER='openai', OPENAI_API_KEY='test')
        self.openai.return_value.chat.completions.create.return_value = iter([])
        with self.assertRaisesRegex(RuntimeError, 'vacía'):
            list(ai_engine.AIEngine().ask_stream('Hola'))

    def test_local_providers_reject_http_errors_before_decoding(self):
        for provider in ('ollama', 'lmstudio', 'llamacpp'):
            with self.subTest(provider=provider):
                os.environ['AI_PROVIDER'] = provider
                response = Mock()
                response.raise_for_status.side_effect = ai_engine.requests.HTTPError('secret-server-details')
                self.post.return_value = response
                with self.assertRaises(RuntimeError) as error:
                    ai_engine.AIEngine().ask('Hola')
                self.assertNotIn('secret-server-details', str(error.exception))
                response.json.assert_not_called()

    def test_local_connection_failure_identifies_offline_server(self):
        os.environ.update(
            AI_PROVIDER='llamacpp',
            LOCAL_CHAT_URL='http://127.0.0.1:8080/v1/chat/completions',
        )
        self.post.side_effect = ai_engine.requests.ConnectionError('internal socket details')
        with self.assertRaisesRegex(RuntimeError, '127.0.0.1:8080') as error:
            ai_engine.AIEngine().ask('Hola')
        self.assertIn('servidor local', str(error.exception).lower())
        self.assertNotIn('internal socket details', str(error.exception))

    def test_local_providers_return_text_and_apply_timeout(self):
        for provider, data in [
            ('ollama', {'response': 'Hola'}),
            ('lmstudio', {'choices': [{'message': {'content': 'Hola'}}]}),
            ('llamacpp', {'choices': [{'message': {'content': 'Hola'}}]}),
        ]:
            with self.subTest(provider=provider):
                os.environ['AI_PROVIDER'] = provider
                self.post.return_value.json.return_value = data
                self.assertEqual(ai_engine.AIEngine().ask('Hola'), 'Hola')
                self.assertEqual(self.post.call_args.kwargs['timeout'], 30)

    def test_llamacpp_uses_configurable_openai_compatible_endpoint(self):
        os.environ.update(
            AI_PROVIDER='llamacpp',
            LOCAL_CHAT_URL='http://127.0.0.1:8080/v1/chat/completions',
            LOCAL_LLM_MODEL='gemma-local',
        )
        self.post.return_value.json.return_value = {
            'choices': [{'message': {'content': 'Hola local'}}]
        }
        self.assertEqual(ai_engine.AIEngine().ask('Hola'), 'Hola local')
        self.assertEqual(
            self.post.call_args.args[0],
            'http://127.0.0.1:8080/v1/chat/completions',
        )
        self.assertEqual(
            self.post.call_args.kwargs['json']['model'], 'gemma-local'
        )

    def test_rejects_empty_and_nontext_responses(self):
        os.environ['GEMINI_API_KEY'] = 'test'
        for text in (None, '', '  ', '**', 42, ['hello']):
            with self.subTest(text=text):
                self.gemini.return_value.models.generate_content.return_value = SimpleNamespace(text=text)
                with self.assertRaises(RuntimeError):
                    ai_engine.AIEngine().ask('Hola')

    def test_malformed_local_json_raises_safe_error(self):
        os.environ['AI_PROVIDER'] = 'ollama'
        self.post.return_value.json.side_effect = ValueError('sensitive-body')
        with self.assertRaises(RuntimeError) as error:
            ai_engine.AIEngine().ask('Hola')
        self.assertNotIn('sensitive-body', str(error.exception))

    def test_client_initialization_failure_is_safe(self):
        os.environ['GEMINI_API_KEY'] = 'test'
        self.gemini.side_effect = ValueError('secret-key')
        engine = ai_engine.AIEngine()
        with self.assertRaises(RuntimeError) as error:
            engine.ask('Hola')
        self.assertNotIn('secret-key', str(error.exception))

    def test_dotenv_is_loaded_from_project_root(self):
        with patch('dotenv.load_dotenv') as load:
            importlib.reload(ai_engine)
        project = Path(ai_engine.__file__).resolve().parents[1] / '.env'
        loaded_paths = [call.args[0] for call in load.call_args_list if call.args]
        self.assertIn(project, loaded_paths)


if __name__ == '__main__':
    unittest.main()
