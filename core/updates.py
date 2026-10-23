"""Comprobador de actualizaciones contra GitHub Releases (sin instalar nada)."""
import json
import logging
from datetime import date, datetime

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from core import app_settings
from core.version import REPO

log = logging.getLogger(__name__)

API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"


def latest_version(timeout: int = 6) -> str | None:
    try:
        response = requests.get(API_URL, timeout=timeout, headers={"Accept": "application/vnd.github+json"})
        response.raise_for_status()
        tag = response.json().get("tag_name", "")
        return tag.lstrip("v") or None
    except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
        log.info("No se pudo consultar la última versión: %s", exc)
        return None


def is_newer(latest: str, current: str) -> bool:
    def parts(version: str):
        try:
            return tuple(int(piece) for piece in version.split(".")[:3])
        except ValueError:
            return (0, 0, 0)
    return parts(latest) > parts(current)


class UpdateCheckWorker(QThread):
    done = pyqtSignal(object)  # str | None

    def run(self):
        self.done.emit(latest_version())


def check_in_background(on_result) -> UpdateCheckWorker:
    """Consulta la versión más reciente en un hilo Qt y avisa vía señal."""
    worker = UpdateCheckWorker()
    worker.done.connect(on_result)
    worker.start()
    return worker


def should_auto_check() -> bool:
    last = str(app_settings.value("updates/last_check") or "")
    return last != date.today().isoformat()


def mark_checked():
    app_settings.set_value("updates/last_check", datetime.now().date().isoformat())
