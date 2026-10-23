# Segundo lote: comportamiento visual

Fecha: 2026-10-20. Estado: implementación y aceptación automática completadas.

## Objetivo

Hacer que el companion comunique su estado sin imágenes nuevas ni mayor carga de IA.
Se conserva el robot vectorial, sin boca, y un único temporizador de interfaz.

## Estados

- `IDLE`: respiración vertical y parpadeo.
- `MOVING`: mirada direccional y radios de rueda en movimiento.
- `LISTENING`: ojos verdes pulsantes y halo.
- `THINKING`: ojos cian asimétricos en movimiento.
- `SPEAKING`: ojos violetas, balanceo y ondas laterales.
- `ERROR`: ojos rojos; permanece visible brevemente y vuelve a reposo.

## Restricciones y aceptación

- Un único `QTimer` a 50 ms para física y dibujo; sin dependencias nuevas.
- Los estados que no son `MOVING` no desplazan la ventana.
- La recuperación de `ERROR` no puede pisar una petición nueva ni ejecutarse al cerrar.
- Movimiento limitado a ambos bordes del área útil.
- Los seis estados deben renderizar con Qt offscreen sin excepción.

La verificación multimonitor, DPI y percepción de fluidez requiere una sesión visible
en Windows y no se sustituye con pruebas offscreen.
