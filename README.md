<p align="center">
  <img src="docs/img/banner.png" alt="Robot Asistente" width="100%">
</p>

# Robot Asistente

[![Windows 10/11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?logo=windows11)](https://github.com/david-d2c2/ROBOT-ASISTENTE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-41CD52?logo=qt&logoColor=white)](https://www.riverbankcomputing.com/software/pyqt/)
[![License: MIT](https://img.shields.io/badge/Licencia-MIT-yellow.svg)](LICENSE)

**BMO-Bot** es un robot compañero que vive en tu escritorio de Windows: camina por la
parte inferior de la pantalla, conversa contigo por texto o por voz, y reacciona con sus
ojos luminosos y su antena a todo lo que pasa — escucha, piensa, habla o se equivoca.
Y sí, tiene **humor ácido**: te contesta con sorna, pero siempre te da lo que le pides.

<p align="center">
  <img src="docs/img/app.png" alt="Robot Asistente en funcionamiento" width="340">
</p>

## ✨ Qué hace

- 🤖 **Personaje 3D** (render estilo Pixar generado con IA) con estados animados: reposo,
  paseo, escucha, pensamiento, habla y error.
- 💬 **Multi proveedor de IA**: Z.AI (GLM), OpenAI, Gemini o modelos locales en tu PC
  (Ollama, LM Studio, llama.cpp).
- 🧠 **Memoria de conversación** configurable y botón para olvidarla al instante.
- ⚡ **Streaming**: ves la respuesta mientras se genera.
- ⏹ **Cancelación** de la consulta en curso.
- 🎤 **Voz**: habla y te responde en voz alta; dictado con Google o **local sin conexión**
  (faster-whisper).
- 🖥️ **Integración Windows**: bandeja del sistema, instancia única, posición y
  preferencias persistentes, multimonitor, cierre seguro.
- 😏 **Personalidad**: sarcasmo divertido, nunca cruel — dardo + solución en dos frases.

## 📦 Instalación

### Opción A — Ejecutable (sin Python)

1. Descarga `RobotAsistente-win64.zip` desde la última
   [**Release**](https://github.com/david-d2c2/ROBOT-ASISTENTE/releases/latest).
2. Descomprímelo donde quieras (por ejemplo `C:\RobotAsistente`).
3. Copia `.env.example` como `.env` **dentro de la carpeta descomprimida** y añade tu
   clave de API (ver [configuración](#-configura-tu-proveedor-env)).
4. Doble clic en `RobotAsistente.exe`. El `.env` nunca se incluye en el paquete: tus
   claves no salen de tu equipo.

> El antivirus o SmartScreen pueden avisar la primera vez porque el binario no está
> firmado: elige «Ejecutar igualmente».

### Opción B — Desde el código

Necesitas **Windows 10/11** y **Python 3.11 o superior**:

```powershell
git clone https://github.com/david-d2c2/ROBOT-ASISTENTE.git
cd ROBOT-ASISTENTE
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env    # y edita .env con tu clave de API
.\.venv\Scripts\python.exe main.py
```

Acceso directo con icono en el escritorio:

```powershell
powershell -ExecutionPolicy Bypass -File .\crear_acceso_directo.ps1
```

## 🔑 Configura tu proveedor (`.env`)

Solo hay que elegir **un** proveedor con `AI_PROVIDER`:

| Proveedor | `.env` |
|---|---|
| **Z.AI (GLM)** | `AI_PROVIDER=zai` · `ZAI_API_KEY=...` · `ZAI_MODEL=glm-4.6` |
| **OpenAI** | `AI_PROVIDER=openai` · `OPENAI_API_KEY=...` · `OPENAI_MODEL=gpt-4.1` |
| **Gemini** | `AI_PROVIDER=gemini` · `GEMINI_API_KEY=...` · `GEMINI_MODEL=...` |
| **Ollama** (local) | `AI_PROVIDER=ollama` · `LOCAL_LLM_MODEL=llama3.2` |
| **LM Studio** (local) | `AI_PROVIDER=lmstudio` |
| **llama.cpp** (local) | `AI_PROVIDER=llamacpp` · `LOCAL_CHAT_URL=http://127.0.0.1:8080/v1/chat/completions` |

Variables opcionales: `CHAT_HISTORY_TURNS` (memoria, 8 por defecto), `ZAI_BASE_URL`
(plan de código de Z.AI), y todo lo de voz abajo. Ver `.env.example` completo.

## 🗣️ Voz y dictado

- **Respuestas habladas** con Edge TTS (necesita Internet): `TTS_VOICE`, `TTS_RATE`,
  `TTS_PITCH` configurables.
- **Dictado**: Google por defecto, o **100 % local** con
  [faster-whisper](https://github.com/SYSTRAN/faster-whisper):

  ```powershell
  .\.venv\Scripts\python.exe -m pip install -r requirements-whisper.txt
  ```

  ```env
  STT_PROVIDER=whisper
  STT_LANGUAGE=es-ES
  WHISPER_MODEL=base
  ```

  El modelo se descarga solo la primera vez (~75 MB para `base`) y luego funciona sin conexión.

## 🕹️ Uso

- **Clic en el robot**: muestra u oculta los controles. Escribe y pulsa Enter, o pulsa 🎤.
- **⏹** cancela la consulta; **Arrastrar** lo coloca donde quieras; camina solo.
- **Clic derecho**: controles, «Olvidar conversación» y «Apagar Robot».
- **✖** lo oculta en la bandeja del sistema; desde la bandeja también se apaga.
- Si pulsas el acceso directo con el robot ya abierto, aparece y se pone delante.
- La posición y el estado de la voz se recuerdan entre sesiones.

## 🔒 Privacidad

- Sin cuentas ni telemetría: el robot habla con el proveedor de IA que **tú** configuras.
- La conversación vive en memoria, nunca en disco; «Olvidar conversación» la borra.
- El micrófono solo se activa cuando lo pides; con `STT_PROVIDER=whisper` el audio
  no sale de tu equipo.
- Tus claves viven en `.env`, que nunca se incluye en el repo ni en el ejecutable.

## 🧪 Tests y empaquetado

```powershell
# Tests (53) sin abrir ventanas
$env:QT_QPA_PLATFORM="offscreen"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Empaquetar tu propio ejecutable (PyInstaller)
.\build_exe.bat    # genera dist\RobotAsistente\RobotAsistente.exe
```

Arquitectura, decisiones e historial de fases en [PROYECTO.md](PROYECTO.md).

## 📄 Licencia

[MIT](LICENSE) — úsalo, modifícalo y compártelo. El render 3D del personaje fue
generado con un modelo de imagen por IA a partir del diseño del propio proyecto.
