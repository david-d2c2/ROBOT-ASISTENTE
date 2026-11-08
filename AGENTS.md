# Instrucciones para agentes de código — ROBOT-ASISTENTE

1. Leer `README.md` y `PROYECTO.md` antes de modificar código. Inventariar lo que existe antes de cada fase y marcar `no consta` lo no comprobable.
2. El proyecto es 100 % en español: código, comentarios, prompts, textos de usuario, README y mensajes de commit («3.X — tema: detalle» o «Arreglado: ...»).
3. Cambios pequeños con commits temáticos: una fase por commit. Nada destructivo sin aprobación.
4. Tests obligatorios antes de commitear:
   `QT_QPA_PLATFORM=offscreen .\.venv\Scripts\python.exe -m unittest discover -s tests`
   Toda función nueva lleva test; todo bug corregido lleva un test de regresión que lo hubiera pillado.
5. La versión vive solo en `core/version.py`; el texto de la release de GitHub vive en `RELEASE_NOTES.md` (lo consume `.github/workflows/ci.yml`).
6. Nunca commitear: `.env`, claves, `logs/`, `build/`, `dist/`, `RobotAsistente-win64.zip` (>100 MB hace rechazar el push). Revisar `git status` antes de cualquier `git add -A`.
7. Releases sin CI (sin créditos de Actions): `build_exe.bat` → `Compress-Archive dist\RobotAsistente\* → RobotAsistente-win64.zip` → `gh release create vX.Y.Z --notes-file RELEASE_NOTES.md RobotAsistente-win64.zip`. Verificar que el zip no contiene `.env`.
8. Qt: la interfaz solo se toca desde el hilo principal; lo lento va en `AIWorker` (QThread) y se comunica por señales. Cuidado con objetos compartidos entre hilos (sqlite no permite compartir conexiones; ver `core/memory_store.py`).
9. Seguridad: sin credenciales en cliente ni en el ejecutable; acciones de escritorio con lista blanca y confirmación; micrófono solo por acción del usuario.
10. No desplegar, publicar releases ni cambiar visibilidad del repo sin aprobación explícita del usuario.
