"""Memoria de largo plazo: hechos que el usuario pide recordar (SQLite)."""
import logging
import sqlite3
from pathlib import Path

from PyQt6.QtCore import QStandardPaths

log = logging.getLogger(__name__)


def db_path() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    directory = Path(base) / "RobotAsistente"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "memoria.db"


class MemoryStore:
    """Hechos explícitos del usuario ('recuerda que...'), persistentes."""

    def __init__(self):
        self._connection: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection | None:
        if self._connection is None:
            try:
                self._connection = sqlite3.connect(db_path())
                self._connection.execute(
                    "CREATE TABLE IF NOT EXISTS memories ("
                    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    " ts TEXT DEFAULT CURRENT_TIMESTAMP,"
                    " content TEXT NOT NULL)"
                )
                self._connection.commit()
            except sqlite3.Error:
                log.exception("No se pudo abrir la memoria de largo plazo")
                self._connection = None
        return self._connection

    def add(self, text: str):
        connection = self._connect()
        if connection is None:
            return
        try:
            connection.execute(
                "INSERT INTO memories (content) VALUES (?)", (text.strip(),)
            )
            connection.commit()
        except sqlite3.Error:
            log.exception("No se pudo guardar el recuerdo")

    def all(self, limit: int = 50) -> list[str]:
        connection = self._connect()
        if connection is None:
            return []
        try:
            rows = connection.execute(
                "SELECT content FROM (SELECT * FROM memories ORDER BY id DESC"
                " LIMIT ?) ORDER BY id ASC",
                (limit,),
            ).fetchall()
            return [row[0] for row in rows]
        except sqlite3.Error:
            log.exception("No se pudo leer la memoria")
            return []

    def clear(self):
        if self._connection is not None:
            try:
                self._connection.execute("DELETE FROM memories")
                self._connection.commit()
            except sqlite3.Error:
                log.exception("No se pudo vaciar la memoria")
            self._connection.close()
            self._connection = None
        path = db_path()
        if path.exists():
            try:
                path.unlink()
            except OSError:
                log.warning("No se pudo borrar %s", path)
