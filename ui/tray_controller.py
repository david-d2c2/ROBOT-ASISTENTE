"""Bandeja del sistema: icono, menú y notificaciones."""
import logging

from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

log = logging.getLogger(__name__)


class TrayController:
    """Monta el icono y el menú de la bandeja; delega las acciones en callbacks."""

    def __init__(self, icon_path: str, tooltip: str, callbacks: dict):
        self.tray = QSystemTrayIcon(QIcon(icon_path))
        self.menu = QMenu()

        show_action = self.menu.addAction("Mostrar u ocultar el robot")
        self.voice_action: QAction = self.menu.addAction("Voz activada")
        self.voice_action.setCheckable(True)
        self.voice_action.setChecked(True)
        if "toggle_voice" in callbacks:
            self.voice_action.toggled.connect(callbacks["toggle_voice"])
        forget_action = self.menu.addAction("Olvidar conversación")
        copy_action = self.menu.addAction("Copiar última respuesta")
        settings_action = self.menu.addAction("⚙ Ajustes...")
        update_action = self.menu.addAction("🔄 Buscar actualizaciones")
        version_suffix = f" ({callbacks['version']})" if callbacks.get("version") else ""
        about_action = self.menu.addAction(f"Acerca de{version_suffix}")
        self._separator = self.menu.addSeparator()
        quit_action = self.menu.addAction("Apagar robot")

        self.tray.setContextMenu(self.menu)
        self.tray.setToolTip(tooltip)
        show_action.triggered.connect(callbacks["toggle_visibility"])
        forget_action.triggered.connect(callbacks["forget"])
        copy_action.triggered.connect(callbacks["copy_answer"])
        settings_action.triggered.connect(callbacks["open_settings"])
        update_action.triggered.connect(callbacks["check_updates"])
        about_action.triggered.connect(callbacks["about"])
        quit_action.triggered.connect(callbacks["quit"])
        self.tray.activated.connect(callbacks["tray_activated"])
        self.tray.show()

    def add_action(self, text: str, callback, checkable: bool = False, checked: bool = False):
        """Añade una acción al bloque principal del menú (antes del separador)."""
        action = QAction(text, self.menu)
        if checkable:
            action.setCheckable(True)
            action.setChecked(checked)
            action.toggled.connect(callback)
        else:
            action.triggered.connect(callback)
        self.menu.insertAction(self._separator, action)
        return action

    def notify(self, title: str, message: str, ms: int = 8000):
        try:
            self.tray.showMessage(title, message, self.tray.icon(), ms)
        except Exception:
            log.warning("No se pudo mostrar la notificación", exc_info=True)

    def set_voice_checked(self, enabled: bool):
        if self.voice_action.isChecked() != enabled:
            self.voice_action.blockSignals(True)
            self.voice_action.setChecked(enabled)
            self.voice_action.blockSignals(False)

    def hide(self):
        self.tray.hide()
