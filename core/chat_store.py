"""Historial de conversación persistente (opcional) en SQLite."""
import logging
import sqlite3
from pathlib import Path

from PyQt6.QtCore import QStandardPaths

from core import app_settings

log = logging.getLogger(__name__)


def db_path() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    directory = Path(base) / "RobotAsistente"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "chat.db"


def enabled() -> bool:
    return bool(app_settings.value("chat/persist"))


class ChatStore:
    """Guarda los turnos si el usuario activó la persistencia; si no, no toca disco."""

    def __init__(self):
        self._connection: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection | None:
        if not enabled():
            return None
        if self._connection is None:
            try:
                self._connection = sqlite3.connect(db_path())
                self._connection.execute(
                    "CREATE TABLE IF NOT EXISTS messages ("
                    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    " ts TEXT DEFAULT CURRENT_TIMESTAMP,"
                    " role TEXT NOT NULL,"
                    " content TEXT NOT NULL)"
                )
                self._connection.commit()
            except sqlite3.Error:
                log.exception("No se pudo abrir el historial persistente")
                self._connection = None
        return self._connection

    def load_recent(self, limit: int = 30) -> list[tuple[str, str]]:
        connection = self._connect()
        if connection is None:
            return []
        try:
            rows = connection.execute(
                "SELECT role, content FROM (SELECT * FROM messages ORDER BY id DESC"
                " LIMIT ?) ORDER BY id ASC",
                (limit,),
            ).fetchall()
            return [(role, content) for role, content in rows]
        except sqlite3.Error:
            log.exception("No se pudo leer el historial persistente")
            return []

    def append(self, role: str, content: str):
        connection = self._connect()
        if connection is None:
            return
        try:
            connection.execute(
                "INSERT INTO messages (role, content) VALUES (?, ?)", (role, content)
            )
            connection.commit()
        except sqlite3.Error:
            log.exception("No se pudo guardar el turno en el historial")

    def close(self):
        if self._connection is not None:
            try:
                self._connection.close()
            finally:
                self._connection = None

    def clear(self):
        if self._connection is not None:
            try:
                self._connection.execute("DELETE FROM messages")
                self._connection.commit()
            except sqlite3.Error:
                log.exception("No se pudo vaciar el historial")
        path = db_path()
        if path.exists():
            try:
                path.unlink()
            except OSError:
                log.warning("No se pudo borrar %s", path)
        if self._connection is not None:
            self._connection.close()
            self._connection = None
