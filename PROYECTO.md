# Robot Asistente de Escritorio

## 1. Objetivo

Robot Asistente es un compañero ligero para Windows que permanece sobre el escritorio,
se desplaza por la parte inferior de la pantalla y permite conversar por texto o voz.
Su cuerpo es un **render 3D real (estilo Pixar) generado con IA**, sobre el que se
animan programáticamente los ojos, la luz de la antena, el halo de escucha y las
ondas de voz. La interfaz sigue una estética sci-fi: burbuja HUD de cristal con
glow cian, input de cristal y botones con degradados neón.

Proveedores de IA admitidos: **Z.AI (GLM)**, OpenAI, Gemini y servidores locales
compatibles (Ollama, LM Studio, llama.cpp).

## 2. Estado actual

La aplicación permite:

- conversar por texto con el proveedor configurado, con **memoria de la conversación**
  (turnos configurables) y comando para olvidarla;
- ver la respuesta **mientras se genera** (streaming en Z.AI, OpenAI y Gemini);
- **cancelar** la consulta en curso con el botón ⏹;
- hablar por micrófono y escuchar la respuesta sintetizada, con **dictado local
  opcional** (faster-whisper) además de Google;
- ocultar el robot a la **bandeja del sistema**; el apagado real vive en el menú
  contextual y en la bandeja;
- **instancia única**: abrir dos veces el acceso directo no duplica el robot;
- recordar **posición y estado de la voz** entre sesiones (QSettings);
- moverse entre **monitores** y recalcular límites al cambiar pantallas o DPI;
- cerrarse de forma segura aunque haya tareas activas, con espera acotada a 8 s;
- ejecutarse desde un acceso directo sin consola o como **ejecutable empaquetado**
  con PyInstaller.

## 3. Trabajo por fases (octubre 2026)

### Fase 1 — Identidad visual

- `assets/robot-body.svg`: cuerpo del personaje con la misma identidad que el icono.
- Ojos, antena luminosa, halo, sombra y ondas de voz se dibujan por estado sobre el
  SVG con `QSvgRenderer`, nítido a cualquier DPI y tamaño (robot de 176 px).
- Eliminado el sistema de sprites WebP muerto y `make_sprites.py`.
- El paseo se pausa mientras se arrastra la ventana.

### Fase 2 — Conversación

- Historial multi-turno en memoria (`CHAT_HISTORY_TURNS`, 8 por defecto) reenviado
  al proveedor; «Olvidar conversación» en menú contextual y bandeja.
- Streaming: la burbuja muestra el texto a medida que llega y mantiene el scroll al final.
- Botón ⏹ que cancela y desbloquea la interfaz; los resultados tardíos se descartan.
- Nuevo proveedor `AI_PROVIDER=zai` (API compatible con OpenAI de Z.AI/GLM).

### Fase 3 — Integración con Windows

- Bandeja de sistema con mostrar/ocultar, voz, olvidar y apagar.
- Instancia única con `QLockFile`.
- Preferencias persistentes con `QSettings` (posición horizontal, voz).
- Cierre robusto: interrumpe el trabajador y los cancelados; si un hilo sigue
  atrapado en E/S tras el timeout, sale de forma forzada.
- Multimonitor: límites por pantalla actual, reacción a conectar/desconectar pantallas.

### Fase 4 — Voz

- TTS configurable: `TTS_VOICE`, `TTS_RATE`, `TTS_PITCH`.
- STT seleccionable: `google` (por defecto) o `whisper` local sin conexión
  (`requirements-whisper.txt` opcional; descarga el modelo en el primer uso).
- La escucha cancelada no transcribe; transcripción vacía = «no entendí».

### Fase 5 — Distribución

- `robot.spec` y `build_exe.bat` generan `dist\RobotAsistente\RobotAsistente.exe`
  sin consola y con el icono, incluidas las utilidades FLAC de SpeechRecognition.
- El ejecutable lee `.env` desde su propia carpeta (o la del proyecto si se ejecuta
  desde él), nunca lo incluye.

## 4. Funcionamiento interno

```text
Texto o micrófono
        │
        ▼
DesktopRobot (hilo principal de Qt)
        │ inicia
        ▼
AIWorker (QThread)
        ├── transcripción opcional (Google o faster-whisper)
        ├── AIEngine.ask_stream() → señales parciales
        └── síntesis y reproducción opcional
        │
        ▼ señales Qt
Burbuja con scroll, estados visuales y controles
```

Qt mantiene los cambios de interfaz en el hilo principal. `AIWorker` realiza las
operaciones lentas; al cancelar se interrumpe y se desconectan sus señales para que
ningún resultado tardío pise el estado de la interfaz.

## 5. Archivos principales

| Ruta | Función |
|---|---|
| `main.py` | Ventana, dibujo SVG + estados, tray, persistencia y coordinación del worker. |
| `core/ai_engine.py` | Proveedores (Z.AI, OpenAI, Gemini, locales), historial y streaming. |
| `core/voice_engine.py` | Micrófono, STT (Google/faster-whisper), síntesis y reproducción. |
| `assets/sprites3d/robot-3d.png` | Cuerpo 3D del robot (generado con IA, fondo recortado). |
| `tools/process_sprite.py` | Clave cromática y recorte del render 3D. |
| `assets/robot-body.svg` | Cuerpo vectorial de respaldo si falta el sprite. |
| `assets/robot-assistant.svg/.ico` | Icono del producto y de la bandeja. |
| `robot.spec`, `build_exe.bat` | Empaquetado del ejecutable con PyInstaller. |
| `requirements-whisper.txt` | Dictado local opcional (faster-whisper). |
| `crear_acceso_directo.ps1` | Crea o actualiza el acceso directo con icono. |
| `tests/` | Pruebas de IA, voz, interfaz y lanzador. |

## 6. Configuración

Copia `.env.example` a `.env` y elige un proveedor:

```env
AI_PROVIDER=zai
ZAI_API_KEY=tu_clave_de_zai
ZAI_MODEL=glm-4.6
```

Para OpenAI: `AI_PROVIDER=openai` con `OPENAI_API_KEY` y `OPENAI_MODEL`.
Para Gemini: `AI_PROVIDER=gemini` con `GEMINI_API_KEY` y `GEMINI_MODEL`.
Para servidores locales: `ollama`, `lmstudio` o `llamacpp` (ver `.env.example`).
Voz y dictado: `TTS_*`, `STT_PROVIDER`, `STT_LANGUAGE`, `WHISPER_*`.

## 7. Instalación y ejecución

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe main.py
powershell -ExecutionPolicy Bypass -File .\crear_acceso_directo.ps1
```

Ejecutable independiente:

```powershell
.\build_exe.bat
```

## 8. Verificación

```powershell
$env:QT_QPA_PLATFORM="offscreen"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

Las pruebas cubren proveedores (incluido Z.AI), streaming, historial, límites,
errores, concurrencia, cancelación, cierre, bandeja, persistencia, estados visuales,
voz (Google y whisper) y estructura del lanzador.

## 9. Mejoras posteriores

1. **Selección de micrófono y voz alternativa offline** (Piper) en la interfaz.
2. **Memoria persistente opcional** en SQLite con controles de borrado.
3. **Acciones de escritorio con permisos** (abrir apps, recordatorios) con lista
   explícita de acciones y confirmación.
4. **Instalador firmado** (Inno Setup) sobre el ejecutable de PyInstaller.
5. **Métricas locales** de latencia y coste aproximado de API.

## 10. Privacidad y seguridad

- `.env` y las claves quedan fuera de Git y no se incluyen en el ejecutable.
- El micrófono solo se activa por acción del usuario; con `STT_PROVIDER=whisper`
  el audio no sale del equipo.
- La conversación vive en memoria: no hay historial persistente; «Olvidar
  conversación» la borra al instante.
- Las preferencias (posición y voz) se guardan localmente con QSettings.
