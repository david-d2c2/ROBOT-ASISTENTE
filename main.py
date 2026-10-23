"""Robot Asistente — punto de entrada.

La lógica vive en ui/robot_window.py (ventana y estados) y core/ (IA, voz,
worker, ajustes). Este fichero solo arranca la aplicación.
"""
import logging
import sys
import os

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from core import single_instance, app_settings
from core.hotkey import register_global_hotkey
from core.logging_setup import configure_logging
from core.version import APP_NAME, ORG_NAME, __version__
from ui.robot_window import DesktopRobot

# Reexportas para compatibilidad (tests y consumo externo).
from core.ai_engine import AIEngine  # noqa: F401
from core.voice_engine import VoiceEngine  # noqa: F401

log = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    log.info("%s v%s arrancando", APP_NAME, __version__)

    lock, notified = single_instance.try_start_single_instance()
    if lock is None:
        app = QApplication(sys.argv)  # necesario para el aviso nativo
        if not notified:
            QMessageBox.warning(
                None,
                APP_NAME,
                f"{APP_NAME} ya está en ejecución.\n"
                "Búscalo en la bandeja del sistema (icono del robot).",
            )
        return 0

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(os.path.join(DesktopRobot.assets_dir(), "robot-assistant.ico")))
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)

    robot = DesktopRobot()
    robot.show()
    robot.start_single_instance_server()

    hotkey_filter = register_global_hotkey(
        app_settings.env("HOTKEY", "Ctrl+Alt+R"), robot.start_listening
    )
    if hotkey_filter is not None:
        app.installNativeEventFilter(hotkey_filter)
    else:
        log.info("Sin atajo global (usa HOTKEY=Ctrl+Shift+Espacio, por ejemplo)")

    exit_code = app.exec()
    log.info("Salida con código %s", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
