import os
import re
from pathlib import Path
import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

# El .env del usuario tiene prioridad (junto al ejecutable); después el del proyecto.
load_dotenv(Path.cwd() / '.env')
load_dotenv(Path(__file__).resolve().parents[1] / '.env')

PERSONA_ACIDO = (
    "Eres BMO-Bot, un pequeño robot compañero de escritorio en Windows con humor ácido. "
    "No tienes boca, te expresas con tus ojos luminosos y una voz robótica suave. "
    "Personalidad: respondón, sarcástico y ligeramente rebelde. Te quejas con gracia, pones pegas y sueltas "
    "dardos con sorna, pero SIEMPRE acabas haciendo lo que te piden, y bien: rebelde en las formas, "
    "impecable en los resultados. Tu sarcasmo es divertido, nunca cruel ni ofensivo, y sin temas oscuros. "
    "Hablas en español de forma concisa (máximo 2 frases cortas por respuesta): una para el dardo y otra para la solución. "
    "REGLA ESTRICTA: Escribe en texto plano natural. NUNCA uses asteriscos (*), ni negritas, ni describas acciones entre asteriscos."
)
PERSONA_NORMAL = (
    "Eres BMO-Bot, un pequeño robot compañero de escritorio en Windows. "
    "No tienes boca, te expresas con tus ojos luminosos y una voz robótica suave. "
    "Eres tierno, curioso y servicial; hablas de forma concisa (máximo 2 frases cortas por respuesta). "
    "REGLA ESTRICTA: Escribe en texto plano natural. NUNCA uses asteriscos (*), ni negritas, ni describas acciones entre asteriscos."
)
PERSONA_TECNICO = (
    "Eres BMO-Bot, un asistente técnico de escritorio en Windows, preciso y directo. "
    "Respondes en español, sin rodeos, con pasos accionables y datos exactos cuando los tienes; "
    "si no estás seguro, lo dices. Máximo 3 frases por respuesta. "
    "REGLA ESTRICTA: Escribe en texto plano natural. NUNCA uses asteriscos (*), ni negritas, ni describas acciones entre asteriscos."
)

PERSONAS = {
    "acido": PERSONA_ACIDO,
    "normal": PERSONA_NORMAL,
    "tecnico": PERSONA_TECNICO,
}

ZAI_DEFAULT_BASE_URL = "https://api.z.ai/api/paas/v4/"

class AIError(RuntimeError):
    """Error de IA seguro para mostrar en la interfaz."""


def _env_int(name, default):
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


class AIEngine:
    def __init__(self):
        self.provider = os.getenv("AI_PROVIDER", "gemini").lower()
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self.openai_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.zai_key = os.getenv("ZAI_API_KEY", "")
        self.zai_model = os.getenv("ZAI_MODEL", "glm-4.6")
        self.zai_base_url = os.getenv("ZAI_BASE_URL", ZAI_DEFAULT_BASE_URL)
        self.local_url = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/api/generate")
        self.local_model = os.getenv("LOCAL_LLM_MODEL", "llama3.2")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        self.history_turns = _env_int("CHAT_HISTORY_TURNS", 8)
        self.persona = os.getenv("PERSONA", "acido").lower()
        self.system_prompt = PERSONAS.get(self.persona, PERSONA_ACIDO)
        default_chat_url = (
            "http://127.0.0.1:8080/v1/chat/completions"
            if self.provider == "llamacpp"
            else "http://127.0.0.1:1234/v1/chat/completions"
        )
        self.local_chat_url = os.getenv("LOCAL_CHAT_URL", default_chat_url)

        self.client = None
        self.openai_client = None
        self.zai_client = None

    # ---- Mensajes e historial ----

    def _chat_messages(self, prompt, history):
        messages = [{"role": "system", "content": self.system_prompt}]
        for entry in (history or [])[-self.history_turns * 2:]:
            role = entry.get("role") if isinstance(entry, dict) else None
            content = entry.get("content") if isinstance(entry, dict) else None
            if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _gemini_contents(self, prompt, history):
        contents = []
        for entry in (history or [])[-self.history_turns * 2:]:
            content = entry.get("content") if isinstance(entry, dict) else None
            if not (isinstance(content, str) and content.strip()):
                continue
            role = "model" if entry.get("role") == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": content}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        return contents

    def _flatten_history(self, history):
        lines = []
        for entry in (history or [])[-self.history_turns * 2:]:
            content = entry.get("content") if isinstance(entry, dict) else None
            if not (isinstance(content, str) and content.strip()):
                continue
            who = "Robot" if entry.get("role") == "assistant" else "Usuario"
            lines.append(f"{who}: {content}")
        return "\n".join(lines)

    # ---- Clientes ----

    def _gemini_client(self):
        if self.client is None:
            self.client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(
                    timeout=30000, retry_options=types.HttpRetryOptions(attempts=1)
                ),
            )
        return self.client

    def _openai_compatible_client(self, api_key, base_url=None):
        from openai import OpenAI
        kwargs = {"api_key": api_key, "timeout": 30, "max_retries": 0}
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAI(**kwargs)

    # ---- Texto (sin streaming) ----

    def _ask_text(self, prompt, history):
        if self.provider == "gemini":
            if not self.api_key.strip():
                raise AIError("Configura GEMINI_API_KEY en el archivo .env.")
            response = self._gemini_client().models.generate_content(
                model=self.gemini_model,
                contents=self._gemini_contents(prompt, history),
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    temperature=0.7,
                )
            )
            return response.text or ""

        if self.provider == "openai":
            if not self.openai_key.strip():
                raise AIError("Configura OPENAI_API_KEY en el archivo .env.")
            if self.openai_client is None:
                self.openai_client = self._openai_compatible_client(self.openai_key)
            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=self._chat_messages(prompt, history),
                temperature=0.7
            )
            return response.choices[0].message.content or ""

        if self.provider == "zai":
            if not self.zai_key.strip():
                raise AIError("Configura ZAI_API_KEY en el archivo .env.")
            if self.zai_client is None:
                self.zai_client = self._openai_compatible_client(
                    self.zai_key, base_url=self.zai_base_url
                )
            response = self.zai_client.chat.completions.create(
                model=self.zai_model,
                messages=self._chat_messages(prompt, history),
                temperature=0.7
            )
            return response.choices[0].message.content or ""

        if self.provider == "ollama":
            flattened = self._flatten_history(history)
            context = f"{flattened}\n" if flattened else ""
            payload = {
                "model": self.local_model,
                "prompt": f"{self.system_prompt}\n{context}Usuario: {prompt}\nRobot:",
                "stream": False
            }
            res = requests.post(self.local_url, json=payload, timeout=30)
            res.raise_for_status()
            return res.json()["response"]

        if self.provider in ("lmstudio", "llamacpp"):
            headers = {"Authorization": "Bearer not-needed"}
            payload = {
                "model": self.local_model,
                "messages": self._chat_messages(prompt, history)
            }
            res = requests.post(self.local_chat_url, json=payload, headers=headers, timeout=30)
            res.raise_for_status()
            return res.json()["choices"][0]["message"]["content"]

        raise AIError(
            "Revisa AI_PROVIDER: proveedor no reconocido; "
            "usa gemini, openai, zai, ollama, lmstudio o llamacpp."
        )

    # ---- Texto (streaming; los proveedores sin streaming devuelven un único bloque) ----

    def _stream_chunks(self, prompt, history):
        if self.provider == "openai":
            if not self.openai_key.strip():
                raise AIError("Configura OPENAI_API_KEY en el archivo .env.")
            if self.openai_client is None:
                self.openai_client = self._openai_compatible_client(self.openai_key)
            stream = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=self._chat_messages(prompt, history),
                temperature=0.7,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is not None and delta.content:
                    yield delta.content

        elif self.provider == "zai":
            if not self.zai_key.strip():
                raise AIError("Configura ZAI_API_KEY en el archivo .env.")
            if self.zai_client is None:
                self.zai_client = self._openai_compatible_client(
                    self.zai_key, base_url=self.zai_base_url
                )
            stream = self.zai_client.chat.completions.create(
                model=self.zai_model,
                messages=self._chat_messages(prompt, history),
                temperature=0.7,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is not None and delta.content:
                    yield delta.content

        elif self.provider == "gemini":
            if not self.api_key.strip():
                raise AIError("Configura GEMINI_API_KEY en el archivo .env.")
            stream = self._gemini_client().models.generate_content_stream(
                model=self.gemini_model,
                contents=self._gemini_contents(prompt, history),
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    temperature=0.7,
                )
            )
            for response in stream:
                if response.text:
                    yield response.text

        else:
            yield self._ask_text(prompt, history)

    def ask(self, prompt: str, history=None) -> str:
        try:
            text = self._ask_text(prompt, history)
            if not isinstance(text, str):
                raise AIError("El proveedor de IA no devolvió una respuesta de texto válida.")
            text = re.sub(r'\*+', '', text).strip()
            if not text:
                raise AIError("El proveedor de IA devolvió una respuesta vacía.")
            return text
        except AIError:
            raise
        except requests.ConnectionError:
            if self.provider in ("ollama", "lmstudio", "llamacpp"):
                endpoint = self.local_url if self.provider == "ollama" else self.local_chat_url
                raise AIError(
                    f"No se puede conectar con el servidor local en {endpoint}. "
                    "Inicia el modelo y mantenlo en línea."
                ) from None
            raise AIError("No se pudo conectar con el proveedor de IA.") from None
        except Exception:
            raise AIError("No se pudo obtener una respuesta de IA. Revisa la conexión, la clave y el modelo configurado.") from None

    def ask_stream(self, prompt: str, history=None):
        """Generador: entrega la respuesta en bloques a medida que llegan."""
        try:
            emitted = False
            for chunk in self._stream_chunks(prompt, history):
                if not chunk:
                    continue
                emitted = True
                yield re.sub(r'\*+', '', chunk)
            if not emitted:
                raise AIError("El proveedor de IA devolvió una respuesta vacía.")
        except AIError:
            raise
        except requests.ConnectionError:
            if self.provider in ("ollama", "lmstudio", "llamacpp"):
                endpoint = self.local_url if self.provider == "ollama" else self.local_chat_url
                raise AIError(
                    f"No se puede conectar con el servidor local en {endpoint}. "
                    "Inicia el modelo y mantenlo en línea."
                ) from None
            raise AIError("No se pudo conectar con el proveedor de IA.") from None
        except Exception:
            raise AIError("No se pudo obtener una respuesta de IA. Revisa la conexión, la clave y el modelo configurado.") from None
