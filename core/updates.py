"""Comprobador y auto-actualizador contra GitHub Releases."""
import json
import logging
import shutil
import subprocess
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from core import app_settings
from core.version import REPO

log = logging.getLogger(__name__)

ASSET_NAME = "RobotAsistente-win64.zip"

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


# ---- Auto-actualización (solo ejecutable empaquetado) ----

def release_asset_url(version: str) -> str:
    return f"https://github.com/{REPO}/releases/download/v{version}/{ASSET_NAME}"


def download_update(version: str, work_dir: Path) -> Path:
    """Descarga el zip de la Release y lo extrae; devuelve la carpeta con el contenido."""
    url = release_asset_url(version)
    work_dir.mkdir(parents=True, exist_ok=True)
    zip_path = work_dir / ASSET_NAME
    log.info("Descargando actualización %s...", version)
    with requests.get(url, stream=True, timeout=600) as response:
        response.raise_for_status()
        with zip_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 20):
                handle.write(chunk)
    extract_dir = work_dir / "contenido"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    try:
        with zipfile.ZipFile(zip_path) as bundle:
            bundle.extractall(extract_dir)
    except zipfile.BadZipFile as exc:
        raise RuntimeError("El paquete descargado no es un zip válido.") from exc
    if not (extract_dir / "RobotAsistente.exe").exists():
        raise RuntimeError("El paquete descargado no contiene RobotAsistente.exe")
    log.info("Actualización extraída en %s", extract_dir)
    return extract_dir


def write_update_bat(extract_dir: Path, install_dir: Path, bat_path: Path) -> Path:
    """Genera un .bat que sustituye la instalación al cerrar el robot y lo relanza."""
    script = (
        "@echo off\r\n"
        "timeout /t 2 /nobreak >nul\r\n"
        f"robocopy \"{extract_dir}\" \"{install_dir}\" /E /IS /IT >nul\r\n"
        f"rmdir /s /q \"{extract_dir}\"\r\n"
        "del \"%~f0\"\r\n"
        f"start \"\" \"{install_dir / 'RobotAsistente.exe'}\"\r\n"
    )
    bat_path.write_text(script, encoding="utf-8")
    return bat_path


def can_self_update() -> bool:
    return getattr(sys, "frozen", False)


class UpdateDownloadWorker(QThread):
    """Descarga y prepara la actualización en un hilo; emite (ok, ruta|error)."""

    done = pyqtSignal(bool, object)

    def __init__(self, version: str):
        super().__init__()
        self.version = version

    def run(self):
        try:
            work_dir = Path.cwd() / "_update"
            extract_dir = download_update(self.version, work_dir)
            bat = write_update_bat(extract_dir, Path.cwd(), Path.cwd() / "actualizar.bat")
            self.done.emit(True, bat)
        except Exception as exc:
            log.exception("Fallo descargando la actualización")
            self.done.emit(False, str(exc))
