"""Tema sci-fi centralizado: skins de color, fuentes y hojas de estilo.

Un 'skin' define el color de acento (ojos en reposo, antena, burbuja y
botones). Los colores de estado (escucha verde, habla violeta, error rojo)
se mantienen fijos para no perder legibilidad.
"""
from PyQt6.QtGui import QColor

GREEN = QColor(0, 255, 140)
VIOLET = QColor(170, 120, 255)
RED = QColor(255, 75, 90)

SKINS = {
    "clasico": QColor(0, 240, 255),
    "matrix": QColor(0, 255, 102),
    "neon": QColor(255, 64, 180),
    "solar": QColor(255, 176, 32),
}

SKIN_LABELS = [
    ("Clásico (cian)", "clasico"),
    ("Matrix (verde)", "matrix"),
    ("Neón (magenta)", "neon"),
    ("Solar (ámbar)", "solar"),
]

_active = QColor(0, 240, 255)


def set_skin(name: str) -> QColor:
    global _active
    _active = SKINS.get(name, SKINS["clasico"])
    return _active


def accent() -> QColor:
    return QColor(_active)


def accent_hex() -> str:
    return _active.name()


def state_color(state: str) -> QColor:
    return {
        "ERROR": RED,
        "LISTENING": GREEN,
        "SPEAKING": VIOLET,
    }.get(state, QColor(_active))


def _a(alpha: int = 255) -> str:
    return f"rgba({_active.red()}, {_active.green()}, {_active.blue()}, {alpha})"


def BUBBLE_QSS() -> str:
    return (
        "QPlainTextEdit {"
        " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        "   stop:0 rgba(8, 14, 26, 242), stop:1 rgba(12, 24, 42, 226));"
        " color: #8FF7FF;"
        f" border: 1px solid {_a(110)};"
        f" border-left: 3px solid {accent_hex()};"
        " border-radius: 12px;"
        " padding: 8px 10px;"
        " }"
    )


def CHAT_QSS() -> str:
    return (
        "QTextBrowser {"
        " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        "   stop:0 rgba(8, 14, 26, 242), stop:1 rgba(12, 24, 42, 226));"
        f" border: 1px solid {_a(110)};"
        f" border-left: 3px solid {accent_hex()};"
        " border-radius: 12px;"
        " padding: 8px 10px;"
        " }"
    )


def INPUT_QSS() -> str:
    return (
        "QLineEdit {"
        " background: rgba(6, 12, 24, 235);"
        " color: #CFF9FF;"
        f" border: 1px solid {_a(90)};"
        " border-radius: 14px;"
        " padding: 5px 10px;"
        " selection-background-color: #00F0FF;"
        " selection-color: #04141C;"
        " }"
        "QLineEdit:focus { border: 1px solid " + accent_hex() + "; background: rgba(10, 20, 36, 245); }"
    )


def MIC_QSS() -> str:
    return (
        "QPushButton {"
        f" background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        f"   stop:0 {_active.lighter(130).name()}, stop:1 {_active.darker(130).name()});"
        " color: #03202B;"
        " border: 1px solid rgba(255, 255, 255, 80);"
        " border-radius: 10px;"
        " font-weight: bold;"
        " }"
        f"QPushButton:hover {{ background: {_active.lighter(150).name()}; }}"
        f"QPushButton:pressed {{ background: {_active.darker(150).name()}; }}"
        "QPushButton:disabled { background: #35414E; color: #6B7A88; border-color: rgba(90,110,125,120); }"
    )


def STOP_QSS() -> str:
    return (
        "QPushButton {"
        " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        "   stop:0 #FFB020, stop:1 #FF7A00);"
        " color: #2B1400;"
        " border: 1px solid rgba(255, 255, 255, 80);"
        " border-radius: 10px;"
        " font-weight: bold;"
        " }"
        "QPushButton:hover { background: #FFC24D; }"
        "QPushButton:disabled { background: #35414E; color: #6B7A88; border-color: rgba(90,110,125,120); }"
    )


def VOICE_QSS() -> str:
    return (
        "QPushButton {"
        " background: rgba(10, 18, 32, 235);"
        " color: #7DE8F7;"
        f" border: 1px solid {_a(110)};"
        " border-radius: 10px;"
        " font-weight: 600;"
        " font-size: 8pt;"
        " }"
        f"QPushButton:hover {{ border: 1px solid {accent_hex()}; color: #B9F8FF; }}"
        f"QPushButton:checked {{ background: {_a(38)}; border: 1px solid {accent_hex()}; color: #E4FDFF; }}"
        "QPushButton:disabled { color: #5B6B7A; border-color: rgba(90, 110, 125, 120); }"
    )


def SETTINGS_QSS() -> str:
    return (
        "QPushButton {"
        " background: rgba(10, 18, 32, 235);"
        " color: #7DE8F7;"
        f" border: 1px solid {_a(110)};"
        " border-radius: 10px;"
        " font-weight: bold;"
        " }"
        f"QPushButton:hover {{ border: 1px solid {accent_hex()}; }}"
    )


def CLOSE_QSS() -> str:
    return (
        "QPushButton {"
        " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        "   stop:0 #FF6B6B, stop:1 #D93131);"
        " color: white;"
        " border: none;"
        " border-radius: 10px;"
        " font-weight: bold;"
        " }"
        "QPushButton:hover { background: #FF8585; }"
        "QPushButton:pressed { background: #B92626; }"
    )
