# Contribuir a Robot Asistente

¡Gracias por el interés! Este documento resume lo necesario para poner el
proyecto en marcha y enviar cambios que encajen a la primera.

## Requisitos

- **Windows 10/11** (el proyecto usa la bandeja del sistema, `os.startfile` y
  hotkeys globales: no está pensado para Linux/macOS).
- **Python 3.11 o superior** y `git`.

## Montar el entorno

```powershell
git clone https://github.com/david-d2c2/ROBOT-ASISTENTE.git
cd ROBOT-ASISTENTE
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env    # y pon tu clave de API del proveedor que elijas
.\.venv\Scripts\python.exe main.py
```

## Ejecutar los tests

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:PYGAME_HIDE_SUPPORT_PROMPT = "1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

La suite corre offscreen (sin abrir ventanas) y también en CI con cada push.
**Un PR debe llegar con la suite verde**: toda función nueva lleva test, y
todo bug corregido lleva un test de regresión que lo hubiera pillado.

## Convenciones

- **Español en todo**: código, comentarios, textos de la interfaz, README y
  mensajes de commit («3.X — tema: detalle», o «Arreglado: ...»).
- **Commits temáticos y pequeños**: una fase o un arreglo por commit.
- **Arquitectura**: `ui/` (ventana, pintado, tema, ajustes) y `core/` (IA, voz,
  worker, ajustes). La interfaz solo se toca desde el hilo principal de Qt;
  el trabajo lento vive en `AIWorker` (QThread) y se comunica por señales.
- **Hilos**: sqlite no permite compartir conexiones entre hilos (ver
  `core/memory_store.py`); los objetos que cruzan hilos van por señales en cola.
- **Seguridad**: ninguna clave en el repo ni en el ejecutable; las acciones de
  escritorio usan lista blanca de apps y confirmación visible; el micrófono
  solo se activa por acción del usuario.

## Releases

- La versión vive en `core/version.py` y el texto de la release en
  `RELEASE_NOTES.md` (lo consume el workflow de GitHub Actions).
- Al publicar un tag `v*`, la CI compila el ejecutable y crea la release con
  el zip. Si la CI no está disponible: `tools/release.ps1 -Publicar` lo hace
  en local (tests, build, verificación del zip y publicación con `gh`).

## Reportar bugs

Abre un issue con: versión (la dice el menú «Acerca de»), proveedor de IA,
pasos exactos para reproducir y, si aplica, el contenido de los logs en
`logs/robot.log` (junto a la app, o en `%AppData%\RobotAsistente` en el
ejecutable). Sin capturas con claves visibles, por favor.
