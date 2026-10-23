"""Logging con rotación: logs/robot.log junto al ejecutable o al proyecto.

En el exe no hay consola: sin esto, cualquier fallo es invisible.
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_NAME = "robot.log"


def logs_dir() -> Path | None:
    directory = Path.cwd() / "logs"
    try:
        directory.mkdir(exist_ok=True)
        return directory
    except OSError:
        return None


def configure_logging() -> Path | None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    directory = logs_dir()
    if directory is not None:
        file_handler = RotatingFileHandler(
            directory / _LOG_NAME, maxBytes=512 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    root.addHandler(console)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    return directory
