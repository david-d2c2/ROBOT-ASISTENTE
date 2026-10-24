"""Ajustes persistentes de la aplicación (QSettings)."""
import os

from PyQt6.QtCore import QSettings

from core.version import ORG_NAME

# Claves conocidas y sus valores por defecto.
DEFAULTS = {
    "window/x": None,
    "window/robot_height": 120,
    "voice/enabled": True,
    "chat/persist": False,
    "actions/enabled": True,
    "actions/allowed_apps": "calc,notepad,mspaint,explorer",
    "actions/always_allow": "",
    "updates/last_check": "",
    "setup/done": False,
    "hands_free": False,
}


def settings() -> QSettings:
    return QSettings(ORG_NAME, ORG_NAME)


def value(key: str):
    default = DEFAULTS.get(key)
    return settings().value(key, default)


def set_value(key: str, val) -> None:
    settings().setValue(key, val)
    settings().sync()


def env(name: str, default: str = "") -> str:
    """Lee un ajuste de entorno con valor por defecto seguro."""
    raw = os.getenv(name, "").strip()
    return raw or default
