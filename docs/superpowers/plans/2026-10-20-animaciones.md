# Comportamiento visual — ejecución

**Goal:** Estados visibles y movimiento expresivo con el dibujo vectorial existente.

**Archivos:** `main.py`, `tests/test_robot.py`, documentación del proyecto.

## Tareas

- [x] Mapear estados, temporizador, pintura, movimiento, activos y pruebas existentes.
- [x] Añadir pruebas de temporizador, bordes, error y renderizado de seis estados.
- [x] Observar fallos previos del intervalo y del estado `ERROR`.
- [x] Implementar expresiones vectoriales, ruedas, hover y recuperación segura.
- [x] Generar y revisar una lámina local de los seis estados; retirar el artefacto temporal.
- [x] Ejecutar la suite completa con IA, voz y Qt simulados.
- [x] Revisar el conjunto de forma independiente y registrar límites sin impacto actual.

## Evidencia

- 20/10/2026: 13 pruebas de interfaz y 37 pruebas totales superadas.
- Suite completa: `.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v`.
- Tiempo de la suite completa: 0,560 s.
- Sin sprites ni dependencias nuevas; un temporizador de 50 ms.
- Pendiente manual: varios monitores, escalado DPI y fluidez visible sostenida.
- Revisión independiente: sin bloqueadores. Si se incorporan WebP, deberá reproducirse
  únicamente el `QMovie` del estado visible. El cruce entre monitores y una preferencia
  para reducir movimiento quedan fuera de este lote.
