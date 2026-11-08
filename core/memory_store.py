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
    """Hechos explícitos del usuario ('recuerda que...'), persistentes.

    Se usa desde el hilo principal (guardar con la acción «remember») y desde
    el hilo del AIWorker (inyectar los recuerdos en el prompt), así que cada
    operación abre y cierra su propia conexión: sqlite no permite compartir
    una conexión entre hilos.
    """

    def _connect(self) -> sqlite3.Connection | None:
        connection = None
        try:
            connection = sqlite3.connect(db_path())
            connection.execute(
                "CREATE TABLE IF NOT EXISTS memories ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " ts TEXT DEFAULT CURRENT_TIMESTAMP,"
                " content TEXT NOT NULL)"
            )
            connection.commit()
            return connection
        except sqlite3.Error:
            log.exception("No se pudo abrir la memoria de largo plazo")
            if connection is not None:
                connection.close()
            return None

    def add(self, text: str):
        text = (text or "").strip()
        if not text:
            return
        connection = self._connect()
        if connection is None:
            return
        try:
            # Recordar dos veces lo mismo no aporta nada: sin duplicados.
            connection.execute("DELETE FROM memories WHERE content = ?", (text,))
            connection.execute("INSERT INTO memories (content) VALUES (?)", (text,))
            connection.commit()
        except sqlite3.Error:
            log.exception("No se pudo guardar el recuerdo")
        finally:
            connection.close()

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
        finally:
            connection.close()

    def remove(self, query: str) -> int:
        """Borra los recuerdos que coincidan exactamente o contengan la
        consulta. Devuelve cuántos se han borrado."""
        query = (query or "").strip()
        if not query:
            return 0
        connection = self._connect()
        if connection is None:
            return 0
        try:
            cursor = connection.execute(
                "DELETE FROM memories WHERE content = ? OR content LIKE ?",
                (query, f"%{query}%"),
            )
            connection.commit()
            return cursor.rowcount
        except sqlite3.Error:
            log.exception("No se pudo olvidar el recuerdo")
            return 0
        finally:
            connection.close()

    def clear(self):
        connection = self._connect()
        if connection is not None:
            try:
                connection.execute("DELETE FROM memories")
                connection.commit()
            except sqlite3.Error:
                log.exception("No se pudo vaciar la memoria")
            finally:
                connection.close()
        path = db_path()
        if path.exists():
            try:
                path.unlink()
            except OSError:
                log.warning("No se pudo borrar %s", path)
