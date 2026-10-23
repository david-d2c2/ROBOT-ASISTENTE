@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo No se encuentra .venv. Ejecuta la preparacion indicada en README.md.
    exit /b 1
)
".venv\Scripts\python.exe" -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Instalando PyInstaller...
    ".venv\Scripts\python.exe" -m pip install pyinstaller || exit /b 1
)
".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm robot.spec || exit /b 1
echo.
echo Listo. Ejecutable: dist\RobotAsistente\RobotAsistente.exe
echo Copia .env junto a la carpeta dist\RobotAsistente o edita dist\RobotAsistente\.env
