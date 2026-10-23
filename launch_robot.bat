@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo No se encuentra .venv. Ejecuta la preparacion indicada en README.md.
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "main.py"
