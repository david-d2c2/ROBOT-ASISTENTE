"""Agente de noticias: cada X minutos busca novedades y las resume con la IA.

El programador y las señales viven en el hilo principal; la descarga y el
resumen (red + proveedor) corren en un QThread con su propio AIEngine, como
hace la prueba de conexión de ajustes. Si no hay novedades o algo falla, no
molesta: queda en el log y reintenta en el siguiente ciclo.
"""
import logging
import time

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

from core import app_settings, news
from core.news import SeenStore, seen_path

log = logging.getLogger(__name__)


class _DigestWorker(QThread):
    """Descarga feeds, filtra lo visto y pide el resumen al proveedor de IA."""
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, feeds: list[str], max_items: int, parent=None):
        super().__init__(parent)
        self.feeds = feeds
        self.max_items = max_items

    def run(self):
        try:
            items = news.fetch_items(self.feeds)
            store = SeenStore(seen_path())
            nuevas = store.filter_new(items)
            store.mark(nuevas)  # se marcan todas: sin acumular backlog antiguas
            if not nuevas:
                return
            seleccion = nuevas[: self.max_items]
            from core.ai_engine import AIEngine
            texto = AIEngine().ask(news.build_digest_prompt(seleccion)).strip()
            if texto:
                self.done.emit(texto)
        except Exception as exc:
            log.warning("Ciclo de noticias falló: %s", exc)
            self.failed.emit(str(exc))


class NewsAgent(QObject):
    """Busca noticias cada X minutos y avisa cuando hay resumen nuevo."""

    digest_ready = pyqtSignal(str)

    def __init__(self, first_delay_ms: int = 20_000, parent=None):
        super().__init__(parent)
        self._worker: _DigestWorker | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(30 * 60_000)  # 30 min; se reajusta en cada ciclo
        self._timer.timeout.connect(self._tick)
        QTimer.singleShot(first_delay_ms, self._start_if_enabled)

    def _start_if_enabled(self):
        if self.enabled():
            self._timer.start(self.interval_minutes() * 60_000)
            self._tick()

    def shutdown(self):
        self._timer.stop()

    # ---- Configuración (se relee en cada ciclo: los cambios aplican en vivo) ----

    def enabled(self) -> bool:
        stored = app_settings.value("news/enabled")
        if stored is not None:
            return bool(stored)
        return app_settings.env("NEWS_ENABLED").lower() in ("1", "true", "yes", "on")

    def set_enabled(self, enabled: bool):
        app_settings.set_value("news/enabled", bool(enabled))
        if enabled and not self._timer.isActive():
            self._timer.start(self.interval_minutes() * 60_000)
            self._tick()
        elif not enabled:
            self._timer.stop()

    def feeds(self) -> list[str]:
        stored = str(app_settings.value("news/feeds") or "").strip()
        raw = stored or app_settings.env("NEWS_FEEDS")
        return [f.strip() for f in raw.split(",") if f.strip()] or news.DEFAULT_FEEDS

    def interval_minutes(self) -> int:
        stored = app_settings.value("news/interval_min")
        try:
            if stored is not None and int(stored) >= 10:
                return int(stored)
        except (TypeError, ValueError):
            pass
        try:
            return max(10, int(app_settings.env("NEWS_INTERVAL_MINUTES", "30")))
        except ValueError:
            return 30

    def max_items(self) -> int:
        try:
            return max(1, min(8, int(app_settings.env("NEWS_MAX_ITEMS", "5"))))
        except ValueError:
            return 5

    # ---- Ciclo ----

    def _tick(self, hour=None):
        if not self.enabled():
            return
        # Intervalo configurable en vivo: se reaplica en cada ciclo.
        self._timer.setInterval(self.interval_minutes() * 60_000)
        hour = time.localtime().tm_hour if hour is None else hour
        start = _int_env("NEWS_START_HOUR", 9)
        end = _int_env("NEWS_END_HOUR", 21)
        if not news.in_active_hours(hour, start, end):
            return
        if self._worker is not None and self._worker.isRunning():
            return  # el ciclo anterior sigue: no solapar
        self._worker = _DigestWorker(self.feeds(), self.max_items())
        self._worker.done.connect(self._on_digest)
        self._worker.failed.connect(lambda _m: None)  # fallo silencioso: log ya
        self._worker.start()

    def _on_digest(self, text: str):
        self.digest_ready.emit(text)


def _int_env(name: str, default: int) -> int:
    try:
        return int(app_settings.env(name, str(default)))
    except ValueError:
        return default
