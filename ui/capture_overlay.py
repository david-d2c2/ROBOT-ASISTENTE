"""Superposición a pantalla completa para seleccionar una región a capturar."""
import logging

from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtGui import QCursor, QPainter, QColor
from PyQt6.QtWidgets import QApplication, QRubberBand, QWidget

log = logging.getLogger(__name__)


class CaptureOverlay(QWidget):
    """Pantalla oscurecida con una lupa de selección; Enter/Esc o clic derecho cancelan."""

    captured = pyqtSignal(object)   # QPixmap
    cancelled = pyqtSignal()

    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        screen = self.screen() or QApplication.primaryScreen()
        self.setGeometry(screen.geometry())
        self._origin = None
        self._band = QRubberBand(QRubberBand.Shape.Rectangle, self)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(4, 8, 16, 70))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._finish(None)
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._band.setGeometry(QRect(self._origin, self._origin))
            self._band.show()
        elif event.button() == Qt.MouseButton.RightButton:
            self._finish(None)

    def mouseMoveEvent(self, event):
        if self._origin is not None:
            self._band.setGeometry(
                QRect(self._origin, event.position().toPoint()).normalized()
            )

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        rect = self._band.geometry().normalized()
        self._origin = None
        self._band.hide()
        if rect.width() < 8 or rect.height() < 8:
            self._finish(None)
            return
        top_left = self.geometry().topLeft() + rect.topLeft()
        pixmap = self.screen().grabWindow(
            0, top_left.x(), top_left.y(), rect.width(), rect.height()
        )
        self._finish(pixmap)

    def _finish(self, pixmap):
        self.close()
        if pixmap is not None and not pixmap.isNull():
            self.captured.emit(pixmap)
        else:
            self.cancelled.emit()

    @staticmethod
    def start_capture(on_captured, on_cancelled) -> "CaptureOverlay | None":
        """Abre la superposición sobre la pantalla bajo el cursor."""
        try:
            overlay = CaptureOverlay()
            overlay.captured.connect(on_captured)
            overlay.cancelled.connect(on_cancelled)
            overlay.showFullScreen()
            overlay.activateWindow()
            return overlay
        except Exception:
            log.exception("No se pudo abrir la captura de pantalla")
            return None
