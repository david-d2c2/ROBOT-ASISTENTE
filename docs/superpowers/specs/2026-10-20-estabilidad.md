# Primer lote: estabilidad de Robot Companion

Fecha: 2026-10-20. Estado: implementación y aceptación automática completadas.

## Problema

El worker inicial redefine `QThread.finished` para entregar texto y aún reproduce voz
después de emitirlo. La ventana puede iniciar otro worker o cerrar sin esperar al anterior.
Además, pygame se inicializa al arrancar y las respuestas largas pueden aumentar la
altura de la ventana fuera del escritorio. El SSD anterior describía módulos inexistentes
y presupuestos de recursos sin mediciones.

## Resultado buscado

Una interacción conserva su worker hasta la finalización nativa de Qt. La ventana
permanece utilizable, comunica fallos y conserva la respuesta escrita si el audio falla.
El cierre solicita interrupción, detiene audio y difiere la destrucción hasta que el worker
termina. No se usa terminación forzada ni espera bloqueante prolongada en el hilo UI.

## Alcance y diseño mínimo

- `main.py`: señales independientes de respuesta/estado/error, un worker activo,
  controles bloqueados mientras está ocupado, cierre común y cooperativo.
- La respuesta llega antes de la voz; el estado SPEAKING representa esa fase.
- Bocadillo desplazable con altura limitada, texto plano y posición acotada a pantalla.
- Silenciado básico de la salida de voz; la captura sigue siendo explícita.
- `core/ai_engine.py`: configuración válida, timeouts y fallos comprensibles sin secretos.
- `core/voice_engine.py`: mezclador diferido, `stop()`, cancelación cooperativa
  `speak(text, should_stop=None)` y limpieza del archivo temporal.
- HTTPS para Google STT, timeout de red STT de 15 s y generación TTS de 30 s.
- Documentación y configuración de ejemplo para reproducir preparación y comprobaciones.

Se conservan estructura, proveedores y dibujo vectorial. No hacen falta nuevas capas,
colas, reintentos automáticos ni dependencias para coordinar el ciclo de vida.

## Contratos de fallo y cancelación

1. Otra pulsación no reemplaza ni duplica el worker activo.
2. STT fallido no consulta IA; IA fallida no se presenta como respuesta hablada normal.
3. TTS fallido conserva texto y restaura controles al final real del worker.
4. Cerrar durante cualquier fase impide nuevas tareas y futuras actualizaciones de UI.
5. La referencia al worker vive hasta `QThread.finished`; después se limpia.
6. Una llamada de red puede retrasar el cierre hasta el timeout de la fase activa.
7. Audio temporal se descarga del mezclador y elimina incluso al fallar o cancelar.
8. La falta de dispositivo de audio no impide iniciar y usar conversación por texto.

## Validación

Tests aislados con dobles para IA, captura y reproducción, sin credenciales ni red real:
concurrencia, estados, errores, cancelación, limpieza, cierre y geometría.
Cada defecto debe tener una regresión que falle con el comportamiento previo.
Comando: `python -m unittest discover -s tests -v` usando el intérprete de `.venv`.

Evidencia automática: 37 pruebas superadas, `pip check` sin conflictos y 7 archivos
Python compilados en memoria. Pruebas manuales pendientes: lanzar en Windows, hablar y escuchar con dispositivos,
silenciar, desconectar Internet, cerrar durante captura/consulta/reproducción, comprobar
respuesta larga y escalado. Los tests aislados no sustituyen estas pruebas.
Registrar resultados y limitaciones en el plan antes de declarar el lote validado.

## Fuera de alcance

Arte nuevo, memoria, voz completamente local, selector de dispositivos, bandeja,
instancia única y medición de CPU/RAM. El siguiente paso es validar este ciclo de
interacción antes de ampliar personalidad visual o funciones persistentes.
