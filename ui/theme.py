"""Tema sci-fi centralizado: colores, fuentes y hojas de estilo."""
from PyQt6.QtGui import QColor

CYAN = QColor(0, 240, 255)
GREEN = QColor(0, 255, 140)
VIOLET = QColor(170, 120, 255)
RED = QColor(255, 75, 90)

STATE_COLORS = {
    "ERROR": RED,
    "LISTENING": GREEN,
    "SPEAKING": VIOLET,
}


def state_color(state: str) -> QColor:
    return STATE_COLORS.get(state, CYAN)


BUBBLE_QSS = (
    "QPlainTextEdit {"
    " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
    "   stop:0 rgba(8, 14, 26, 242), stop:1 rgba(12, 24, 42, 226));"
    " color: #8FF7FF;"
    " border: 1px solid rgba(0, 240, 255, 110);"
    " border-left: 3px solid #00F0FF;"
    " border-radius: 12px;"
    " padding: 8px 10px;"
    " }"
)

INPUT_QSS = (
    "QLineEdit {"
    " background: rgba(6, 12, 24, 235);"
    " color: #CFF9FF;"
    " border: 1px solid rgba(0, 240, 255, 90);"
    " border-radius: 14px;"
    " padding: 5px 10px;"
    " selection-background-color: #00F0FF;"
    " selection-color: #04141C;"
    " }"
    "QLineEdit:focus { border: 1px solid #00F0FF; background: rgba(10, 20, 36, 245); }"
)

MIC_QSS = (
    "QPushButton {"
    " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
    "   stop:0 #12E4FF, stop:1 #00A9C2);"
    " color: #03202B;"
    " border: 1px solid rgba(255, 255, 255, 80);"
    " border-radius: 10px;"
    " font-weight: bold;"
    " }"
    "QPushButton:hover { background: #35EBFF; }"
    "QPushButton:pressed { background: #0093AB; }"
    "QPushButton:disabled { background: #35414E; color: #6B7A88; border-color: rgba(90,110,125,120); }"
)

STOP_QSS = (
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

VOICE_QSS = (
    "QPushButton {"
    " background: rgba(10, 18, 32, 235);"
    " color: #7DE8F7;"
    " border: 1px solid rgba(0, 240, 255, 110);"
    " border-radius: 10px;"
    " font-weight: 600;"
    " font-size: 8pt;"
    " }"
    "QPushButton:hover { border: 1px solid #00F0FF; color: #B9F8FF; }"
    "QPushButton:checked { background: rgba(0, 240, 255, 38); border: 1px solid #00F0FF; color: #E4FDFF; }"
    "QPushButton:disabled { color: #5B6B7A; border-color: rgba(90, 110, 125, 120); }"
)

CLOSE_QSS = (
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

SETTINGS_QSS = (
    "QPushButton {"
    " background: rgba(10, 18, 32, 235);"
    " color: #7DE8F7;"
    " border: 1px solid rgba(0, 240, 255, 110);"
    " border-radius: 10px;"
    " font-weight: bold;"
    " }"
    "QPushButton:hover { border: 1px solid #00F0FF; color: #B9F8FF; }"
)

CHAT_QSS = (
    "QTextBrowser {"
    " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
    "   stop:0 rgba(8, 14, 26, 242), stop:1 rgba(12, 24, 42, 226));"
    " border: 1px solid rgba(0, 240, 255, 110);"
    " border-left: 3px solid #00F0FF;"
    " border-radius: 12px;"
    " padding: 8px 10px;"
    " }"
)
