Correcciones sobre la 3.3:

- 🧠 **Arreglado**: la memoria de largo plazo no se aplicaba al conversar
  (fallaba al cruzar hilos). Ahora «recuerda que...» funciona de verdad: lo
  guarda, lo recuerda en las siguientes conversaciones y no duplica lo que
  ya sabe.
- 🛠️ **Robustez**: los recordatorios y el pomodoro avisan también en la
  conversación (y por voz), no solo en la bandeja del sistema; empezar otro
  pomodoro sustituye al anterior; las habilidades locales se cargan una sola
  vez en vez de releerse en cada mensaje; cualquier error al guardar ajustes
  se muestra en el diálogo sin cerrar nada; los fallos en hilos quedan
  registrados en el log en lugar de perderse.
- Incluye todo lo de 3.3: memoria de largo plazo, habilidades locales,
  pomodoro, saludo por hora, y todos los arreglos del guardado de ajustes.
- 132 tests automatizados.
