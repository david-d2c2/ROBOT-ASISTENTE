Serie 3.4:

- ⏰ **Tareas programadas**: «recuérdame cada día a las 9 la ropa» y el robot
  te avisa a esa hora (bandeja, chat y voz). La agenda persiste entre
  sesiones, y «cancela el aviso de la ropa» la quita.
- 🧩 **Habilidades con acciones**: un JSON en `skills/` puede declarar
  acciones locales (abrir webs, apps, pomodoros, notas...) que el robot
  ejecuta siempre pidiendo confirmación; funcionan por texto y por voz.
- 🧠 **Memoria más flexible**: «olvida que...» borra un recuerdo concreto,
  «🧠 Ver lo que sabe de mí» muestra la lista completa, y los recuerdos no
  se duplican.
- 🎙️ **Micrófono por nombre**: se recuerda el dispositivo elegido por su
  nombre, inmune a que Windows cambie los índices al reiniciar.
- 🤝 **CONTRIBUTING.md**: guía para quienes quieran colaborar en el repo
  público (entorno, tests, convenciones y releases).
- Incluye todo lo de 3.3.1: memoria entre hilos arreglada y mejoras de
  robustez (avisos en el chat, pomodoro sustituible, caché de habilidades).
- 157 tests automatizados.
