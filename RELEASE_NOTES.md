Serie 5.2 — el robot cobra vida:

- 👀 **Sus ojos siguen tu cursor** allá donde esté, no solo cuando pasas
  por encima: la mirada es proporcional a la distancia y vuelve al neutro.
- 👄 **Boca animada**: al hablar, la boca se abre y cierra con la onda de la
  voz (y sonríe cuando está feliz).
- 😊 **Emociones**: feliz un rato tras cada respuesta, confuso si cancelas a
  medias, sorprendido al tocarlo y dormido (con zZ flotando) si llevas un
  rato sin hacerle caso o es de noche.
- 🌙 **Modo noche** (22:00–08:00, `NIGHT_MODE`): paseo más lento y cara de
  sueño; se despierta con cualquier interacción.
- 🏎️ **Movimiento con física**: el paseo acelera al arrancar y frena antes de
  pararse a mirarte; las ruedas giran acorde a la velocidad real.
- ✋ **Arrastre arreglado y con sensación física**: arrastrar al robot se
  perdió por un refactor en la 3.0 — vuelve a funcionar, y al soltar derrapa
  con inercia y **aterriza con squash & stretch** (se aplasta y recupera).
- 189 tests automatizados (12 nuevos de mirada, emociones, noche, easing e
  inercia, incluida la regresión del arrastre).
