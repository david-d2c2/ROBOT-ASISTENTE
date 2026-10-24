# -*- mode: python ; coding: utf-8 -*-
# Empaquetado de Robot Asistente (onedir, sin consola).
# Uso: .venv\Scripts\python.exe -m PyInstaller --clean --noconfirm robot.spec
import os
from PyInstaller.utils.hooks import collect_data_files

datas = [
    ("assets/robot-assistant.ico", "assets"),
    ("assets/robot-assistant.svg", "assets"),
    ("assets/robot-body.svg", "assets"),
    ("assets/sprites3d/robot-3d.png", "assets/sprites3d"),
    ("assets/sprites3d/robot-side.png", "assets/sprites3d"),
    (".env.example", "."),
]
# SpeechRecognition necesita sus utilidades FLAC para transcribir.
datas += [(src, "speech_recognition") for src, _ in collect_data_files("speech_recognition")]

a = Analysis(
    ["main.py"],
    pathex=[os.path.abspath(".")],
    binaries=[],
    datas=datas,
    hiddenimports=["PyQt6.QtSvg", "speech_recognition", "edge_tts", "pygame", "piper"],
    excludes=["tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RobotAsistente",
    icon="assets/robot-assistant.ico",
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="RobotAsistente",
)
