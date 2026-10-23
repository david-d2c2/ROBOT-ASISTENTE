"""Acciones de escritorio seguras.

Protocolo agnóstico del proveedor: el modelo responde con un objeto JSON
cuando el usuario pide algo ejecutable. Antes de ejecutar nada hay lista
blanca de apps y confirmación visible en la interfaz.
"""
import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QTimer

from core import app_settings

log = logging.getLogger(__name__)

KNOWN_ACTIONS = {"open_app", "open_url", "reminder", "note"}
URL_SCHEMES = ("http://", "https://")


def allowed_apps() -> list[str]:
    raw = str(app_settings.value("actions/allowed_apps") or "")
    return [app.strip().lower() for app in raw.split(",") if app.strip()]


def always_allowed() -> set[str]:
    raw = str(app_settings.value("actions/always_allow") or "")
    return {kind.strip() for kind in raw.split(",") if kind.strip()}


def allow_kind(kind: str):
    kinds = sorted(always_allowed() | {kind})
    app_settings.set_value("actions/always_allow", ",".join(kinds))


def build_prompt_instructions() -> str:
    apps = ", ".join(allowed_apps()) or "(ninguna)"
    return (
        "ACCIONES DE ESCRITORIO: cuando el usuario pida una acción ejecutable, responde "
        "ÚNICAMENTE con un objeto JSON válido, sin texto antes ni después. Acciones disponibles: "
        '{"action": "open_app", "app": "<nombre>"} abre una app de esta lista permitida: [' + apps + "]; "
        '{"action": "open_url", "url": "<https://...>"} abre una web; '
        '{"action": "reminder", "minutes": <número>, "message": "<texto>"} crea un recordatorio; '
        '{"action": "note", "text": "<texto>"} guarda una nota. '
        "Si el nombre de app no está en la lista permitida, responde con JSON de todas formas: "
        "el sistema lo denegará con seguridad. Si la petición no es una acción, responde texto normal. "
        "Nunca inventes acciones distintas de estas."
    )


def extract_action(text: str) -> dict | None:
    """Extrae el primer objeto JSON con una acción conocida de la respuesta."""
    if not text or "{" not in text:
        return None
    candidate = text[text.index("{"): text.rindex("}") + 1]
    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(data, dict) and data.get("action") in KNOWN_ACTIONS:
        return data
    return None


def describe(action: dict) -> str:
    kind = action.get("action")
    if kind == "open_app":
        return f"Abrir la aplicación «{action.get('app', '?')}»"
    if kind == "open_url":
        return f"Abrir la web «{action.get('url', '?')}»"
    if kind == "reminder":
        minutes = action.get("minutes", "?")
        return f"Crear un recordatorio en {minutes} min: «{action.get('message', '')}»"
    if kind == "note":
        return f"Guardar una nota: «{str(action.get('text', ''))[:120]}»"
    return str(action)


def notes_path() -> Path:
    return Path.cwd() / "data" / "notas.txt"


def execute(action: dict, tray) -> tuple[bool, str]:
    """Ejecuta la acción ya confirmada. Devuelve (éxito, mensaje para el chat)."""
    kind = action.get("action")
    try:
        if kind == "open_app":
            app = str(action.get("app", "")).strip()
            if app.lower() not in allowed_apps():
                return False, f"⛔ «{app}» no está en la lista de apps permitidas."
            subprocess.Popen(["cmd", "/c", "start", "", app], shell=False)
            return True, f"✅ Abierto: {app}"

        if kind == "open_url":
            url = str(action.get("url", "")).strip()
            if not url.lower().startswith(URL_SCHEMES):
                return False, "⛔ Solo puedo abrir direcciones http(s)."
            os.startfile(url)  # noqa: S606 — validado esquema arriba
            return True, f"✅ Abriendo {url}"

        if kind == "reminder":
            minutes = max(0.1, float(action.get("minutes", 1)))
            message = str(action.get("message") or "Recordatorio")
            QTimer.singleShot(
                int(minutes * 60_000),
                lambda: _notify(tray, "Recordatorio", message),
            )
            return True, f"⏰ Vale, te aviso en {minutes:g} min: «{message}»"

        if kind == "note":
            text = str(action.get("text", "")).strip()
            if not text:
                return False, "⛔ La nota venía vacía."
            path = notes_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"[{datetime.now():%Y-%m-%d %H:%M}] {text}\n")
            return True, f"📝 Nota guardada en {path.name}."
    except Exception as exc:
        log.warning("Acción %s falló: %s", kind, exc)
        return False, "⛔ La acción falló al ejecutarse."
    return False, "⛔ Acción desconocida."


def _notify(tray, title: str, message: str):
    try:
        if tray is not None:
            tray.showMessage(title, message, tray.icon(), 8000)
    except Exception:
        log.warning("No se pudo mostrar la notificación", exc_info=True)
