"""Atajo global de teclado (push-to-talk) vía RegisterHotKey de Windows."""
import ctypes
import ctypes.wintypes as wintypes
import logging

from PyQt6.QtCore import QAbstractNativeEventFilter

log = logging.getLogger(__name__)

WM_HOTKEY = 0x0312
MOD_MAP = {"ctrl": 0x0002, "control": 0x0002, "alt": 0x0001, "shift": 0x0004, "win": 0x0008}
MOD_ORDER = [(0x0002, "ctrl"), (0x0001, "alt"), (0x0004, "shift"), (0x0008, "win")]


def parse_hotkey(combo: str) -> tuple[int, int] | None:
    """'Ctrl+Alt+R' → (modificadores, tecla virtual). None si no es válida.

    Exige al menos un modificador (un atajo global sin él secuestraría la tecla
    en todo el sistema) y una tecla ASCII alfanumérica o de función.
    """
    parts = [part.strip().lower() for part in combo.split("+") if part.strip()]
    if len(parts) < 2:
        return None
    mods = 0
    for part in parts[:-1]:
        if part not in MOD_MAP:
            return None
        mods |= MOD_MAP[part]
    key = parts[-1]
    if len(key) == 1 and key.isascii() and key.isalnum():
        return mods, ord(key.upper())
    if len(key) in (2, 3) and key[0] == "f" and key[1:].isdigit():
        number = int(key[1:])
        if 1 <= number <= 24:
            return mods, 0x70 + number - 1
    return None


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, hotkey_id: int, callback):
        super().__init__()
        self.hotkey_id = hotkey_id
        self.callback = callback

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (API de Qt)
        if event_type == b"windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and msg.wParam == self.hotkey_id:
                    self.callback()
            except Exception:
                log.warning("Fallo procesando el atajo global", exc_info=True)
        return False, 0


def register_global_hotkey(combo: str, callback) -> HotkeyFilter | None:
    """Registra el atajo global; devuelve el filtro o None si no pudo."""
    parsed = parse_hotkey(combo)
    if parsed is None:
        log.warning("Atajo global no válido: %r", combo)
        return None
    mods, vk = parsed
    hotkey_id = 0xB10B
    try:
        if not ctypes.windll.user32.RegisterHotKey(None, hotkey_id, mods, vk):
            log.warning("El atajo global %r está en uso por otra aplicación", combo)
            return None
    except AttributeError:
        return None  # plataforma sin user32
    log.info("Atajo global registrado: %s", combo)
    return HotkeyFilter(hotkey_id, callback)
