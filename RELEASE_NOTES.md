Serie 5.1 — tercer motor de voz local:

- 🎙️ **Zonos local, de alta calidad y sin Pinokio**: nuevo motor TTS con
  instalación propia dentro del robot (`pip install -r requirements-zonos.txt`,
  ~3 GB con PyTorch, GPU recomendable). Se activa con `TTS_PROVIDER=zonos`
  o desde ⚙ Ajustes, funciona 100 % sin Internet y no depende de ningún
  servicio externo.
- 🧬 **Clona tu voz**: apunta `ZONOS_REFERENCE` a un WAV tuyo de 10-30 s y el
  robot hablará con tu voz; sin referencia, usa una voz neutra en español.
- Detecta automáticamente GPU (CUDA) y cae a CPU con aviso; el modelo se
  carga una sola vez y libera VRAM tras cada frase. Mensajes de error
  claros si falta el paquete o el WAV de referencia.
- Incluye todo lo de 5.0 (noticias periódicas) y la serie 3 completa.
- 177 tests automatizados.
