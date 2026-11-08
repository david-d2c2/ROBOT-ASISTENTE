"""Tareas programadas persistentes («recuérdamelo cada día a las 9»).

La agenda vive en un JSON en AppData y sobrevive a reinicios. Un QTimer
comprueba cada 30 s si la hora del sistema coincide con alguna tarea
(dos comprobaciones por minuto: no se puede perder una). Límite conocido:
si el equipo duerme justo a la hora programada, el aviso se pierde.
"""
import json
import logging
import re
import time
from pathlib import Path

from PyQt6.QtCore import QStandardPaths, QTimer

log = logging.getLogger(__name__)

TIME_RE = re.compile(r"^(\d{1,2}):(\d{1,2})$")


def agenda_path() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    directory = Path(base) / "RobotAsistente"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "agenda.json"


def normalize_time(raw: str) -> str:
    """Acepta '9:5' o '09:05' y devuelve '09:05'; ValueError si es inválida."""
    match = TIME_RE.match(str(raw or "").strip())
    if not match:
        raise ValueError(f"Hora inválida: «{raw}» (usa HH:MM, por ejemplo 09:00)")
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError(f"Hora fuera de rango: «{raw}»")
    return f"{hour:02d}:{minute:02d}"


class Scheduler:
    """Avisos a una hora del día, persistentes. Vive en el hilo principal."""

    def __init__(self, on_due=None, check_ms: int = 30_000):
        self._tasks: list[dict] = []
        self.on_due = on_due
        self._load()
        self._timer = QTimer()
        self._timer.setInterval(check_ms)
        self._timer.timeout.connect(self._check)
        self._timer.start()

    def stop(self):
        self._timer.stop()

    # ---- Agenda ----

    def add(self, time_str: str, message: str, repeat: str = "daily") -> dict:
        normalized = normalize_time(time_str)
        message = str(message or "Recordatorio").strip() or "Recordatorio"
        task = {
            "id": max((t["id"] for t in self._tasks), default=0) + 1,
            "time": normalized,
            "message": message,
            "repeat": "once" if str(repeat).lower() in ("once", "una vez") else "daily",
            "last_fired": None,
        }
        self._tasks.append(task)
        self._save()
        return task

    def remove_matching(self, query: str) -> int:
        """Quita las tareas cuyo mensaje o hora contenga la consulta."""
        query = (query or "").strip().lower()
        if not query:
            return 0
        antes = len(self._tasks)
        self._tasks = [
            t for t in self._tasks
            if query not in t["message"].lower() and query != t["time"]
        ]
        borradas = antes - len(self._tasks)
        if borradas:
            self._save()
        return borradas

    def all(self) -> list[dict]:
        return list(self._tasks)

    # ---- Disparo ----

    def _check(self, now=None):
        """Dispara las tareas cuya hora coincide con este minuto."""
        current = now or time.localtime()
        hora = f"{current.tm_hour:02d}:{current.tm_min:02d}"
        hoy = f"{current.tm_year:04d}-{current.tm_mon:02d}-{current.tm_mday:02d}"
        disparadas = []
        for task in self._tasks:
            if task["time"] == hora and task.get("last_fired") != hoy:
                task["last_fired"] = hoy
                disparadas.append(task)
        if not disparadas:
            return
        self._tasks = [t for t in self._tasks if not (t in disparadas and t["repeat"] == "once")]
        self._save()
        for task in disparadas:
            log.info("Tarea programada: «%s» (%s)", task["message"], task["time"])
            try:
                if self.on_due is not None:
                    self.on_due(task)
            except Exception:
                log.exception("El aviso programado falló en el receptor")

    # ---- Persistencia ----

    def _load(self):
        path = agenda_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._tasks = [t for t in data if isinstance(t, dict) and TIME_RE.match(str(t.get("time", "")))]
        except (json.JSONDecodeError, OSError):
            log.exception("No se pudo leer la agenda")
            self._tasks = []

    def _save(self):
        try:
            agenda_path().write_text(
                json.dumps(self._tasks, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        except OSError:
            log.exception("No se pudo guardar la agenda")
