# Estabilidad inicial — plan de implementación

> **For agentic workers:** Use superpowers:executing-plans y test-driven-development. Ejecutar por tareas y registrar evidencia.

**Goal:** Documentar el proyecto real y entregar una primera versión que controle sus tareas y se recupere de fallos de IA/voz.

**Architecture:** Conservar PyQt6, AIWorker y los dos motores actuales. Un único trabajo activo emite respuesta, estado y error; la señal nativa finished libera el trabajo. El cierre solicita interrupción y espera de forma asíncrona, sin destruir un hilo activo.

**Tech Stack:** Python 3.12 instalado, PyQt6, google-genai, requests, Edge TTS, SpeechRecognition y pygame; unittest de biblioteca estándar.

**Spec:** `../specs/2026-10-20-estabilidad.md`; documento principal `../../../SSD Robot Companion de Escritorio.md`.

## Restricciones

- Windows; conservar apariencia, rutas y proveedores existentes. No modificar `.env` ni mostrar claves.
- No llamadas reales a IA, captura de micrófono ni reproducción durante pruebas automáticas.
- Sin nuevas dependencias de ejecución en este lote. Sin repositorio Git existente: no crear commits.
- Gráficos nuevos, memoria conversacional y voz totalmente local quedan en la hoja de ruta.

## Foco de revisión

- Doble envío y clic durante una petición: no duplicar trabajo ni perder el estado.
- Cierre mientras escucha/piensa/habla: mantener vivo el hilo hasta terminar; omitir trabajo posterior.
- Fallo de salida de audio o TTS: conservar respuesta y recuperar controles.
- Credenciales ausentes, respuesta vacía o HTTP de error: mensaje útil sin revelar excepciones internas.
- Respuesta muy larga o arrastre fuera de límites: texto accesible y ventana dentro del área útil.

## Tareas

### 1. Documento y especificación
- [x] Reescribir SSD con arquitectura real, privacidad, estados, estructura, criterios de aceptación y roadmap.
- [x] Añadir README de instalación, arranque, pruebas y diagnóstico; no afirmar verificación manual pendiente.

### 2. Voz tolerante a fallos
Archivos: `core/voice_engine.py`, `tests/test_voice_engine.py`.
Contrato: `listen() -> tuple[bool, str]`, `speak(text, should_stop=None)`, `stop()`.
- [x] Probar constructor sin dispositivo, cancelación, cleanup y configuración de transcripción; observar fallos.
- [x] Inicializar mixer al hablar; TTS con límite total 30 s; STT por HTTPS con espera de red 15 s.
- [x] Pasar suite del módulo sin dispositivos ni red.

### 3. IA tolerante a fallos
Archivos: `core/ai_engine.py`, `tests/test_ai_engine.py`.
Contrato: `ask(prompt) -> str`, `AIError(RuntimeError)` para errores aptos para mostrar al usuario.
- [x] Probar credenciales ausentes, HTTP de error, respuestas vacías/malformadas y tiempos máximos.
- [x] Clientes diferidos, timeout 30 s, errores claros; preservar selección de modelos/proveedores.
- [x] Pasar suite del módulo con transporte simulado.

### 4. Ciclo de interacción e interfaz
Archivos: `main.py`, `tests/test_robot.py`.
- [x] Escribir pruebas de doble envío, voz fallida, estados, cierre y respuesta larga; comprobar fallos iniciales.
- [x] Usar answer_ready/state_changed/failed y finished nativo; bloquear entradas hasta terminar.
- [x] Cierre asíncrono con interrupción cooperativa y parada de reproducción; control de voz.
- [x] Bocadillo de texto plano con scroll y posición limitada al área útil.
- [x] Ejecutar pruebas reales de Qt offscreen con motores simulados.

### 5. Instalación y verificación final
Archivos: `requirements.txt`, `requirements-art.txt`, `.env.example`, `.gitignore`, `launch_robot.bat`.
- [x] Declarar dependencias instaladas y Pillow opcional para el generador; no instalar paquetes.
- [x] Lanzador relativo con comprobación de entorno; proteger secretos/temporales en futuras versiones Git.
- [x] Suite completa: `.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v`.
- [x] `pip check`, sintaxis y revisión independiente del conjunto; corregir hallazgos importantes.
- [x] Actualizar documentación con resultados y límites reales de verificación.

## Evidencia y decisiones

- Base auditada en la conversación anterior: doble envío, estado IDLE antes de TTS y bocadillo fuera de pantalla reproducidos con Qt offscreen.
- Autorización del usuario: preparar documento y empezar mejoras; ejecución directa del primer lote sin otra aprobación de diseño.
- Este plan se conserva como registro, ya que no existe historial Git.
- 20/10/2026: 37 pruebas superadas con transporte, audio y Qt simulados; `pip check`
  sin conflictos; 7 archivos Python compilados en memoria. Audio, micrófono, Gemini y
  servidor local reales quedan para validación manual.
- Revisión independiente: sin bloqueadores; se corrigió la exposición de detalles internos
  en errores de voz y se completaron las referencias a llama.cpp.
