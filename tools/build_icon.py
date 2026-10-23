import os
import struct
import sys
from pathlib import Path

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication


ROOT = Path(__file__).resolve().parents[1]
SIZES = (16, 24, 32, 48, 64, 128, 256)


def build_icon():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication(sys.argv[:1])
    source = QIcon(str(ROOT / "assets" / "robot-assistant.svg"))
    if source.isNull():
        raise RuntimeError("No se pudo cargar el SVG del robot")

    images = []
    for size in SIZES:
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not source.pixmap(size, size).save(buffer, "PNG"):
            raise RuntimeError(f"No se pudo generar el icono de {size}px")
        images.append(bytes(data))

    offset = 6 + 16 * len(images)
    entries = []
    for size, image in zip(SIZES, images):
        dimension = 0 if size == 256 else size
        entries.append(struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(image), offset))
        offset += len(image)

    target = ROOT / "assets" / "robot-assistant.ico"
    target.write_bytes(struct.pack("<HHH", 0, 1, len(images)) + b"".join(entries) + b"".join(images))
    assert target.read_bytes()[:6] == struct.pack("<HHH", 0, 1, len(SIZES))
    return app


if __name__ == "__main__":
    build_icon()
