"""Instancia única: lock + servidor local para despertar al robot vivo."""
import logging
import os

from PyQt6.QtCore import QLockFile
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)

NAME = "robot-asistente"


def _lock_path() -> str:
    return os.path.join(os.environ.get("TEMP", os.getcwd()), "robot-asistente.lock")


def try_start_single_instance() -> tuple[QLockFile | None, bool]:
    """Devuelve (lock, avisado).

    - (lock, False): somos la primera instancia.
    - (None, True): ya hay un robot vivo y se le ha pedido mostrarse.
    - (None, False): el lock está ocupado y no hemos podido contactar.
    """
    lock = QLockFile(_lock_path())
    if lock.tryLock(100):
        return lock, False
    log.info("Instancia ya en ejecución; solicitando que se muestre")
    return None, wake_existing()


def wake_existing() -> bool:
    socket = QLocalSocket()
    socket.connectToServer(NAME)
    connected = socket.waitForConnected(500)
    if connected:
        socket.write(b"show\n")
        socket.flush()
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
    socket.abort()
    return connected


def start_instance_server(on_show) -> QLocalServer:
    """Atiende a lanzamientos posteriores: traen el robot a primer plano."""
    QLocalServer.removeServer(NAME)

    server = QLocalServer()

    def _accept():
        while server.hasPendingConnections():
            connection = server.nextPendingConnection()
            if connection is not None:
                connection.disconnectFromServer()
        log.debug("Lanzamiento secundario recibido; mostrando el robot")
        on_show()

    server.newConnection.connect(_accept)
    if not server.listen(NAME):
        log.warning("No se pudo abrir el servidor de instancia única: %s", server.errorString())
    return server
