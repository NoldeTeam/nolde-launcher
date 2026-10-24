"""Create the application icon: nolde_launcher/ui/assets/images/nolde.ico (+ nolde.png).

A rounded accent-blue tile with a bold "N" set in the bundled Space Grotesk font. The .ico holds
several sizes, each stored as PNG, which Windows reads directly (Vista and later).
Run from the project root:  python scripts/make_icon.py
"""

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice, Qt, QRectF
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QImage, QPainter, QPainterPath

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "nolde_launcher/ui/assets/fonts/SpaceGrotesk-Bold.ttf"
OUT_DIR = ROOT / "nolde_launcher/ui/assets/images"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    radius = size * 0.22
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    painter.fillPath(path, QColor("#2f6fed"))
    font_id = QFontDatabase.addApplicationFont(str(FONT))
    family = QFontDatabase.applicationFontFamilies(font_id)[0]
    font = QFont(family)
    font.setWeight(QFont.Weight.Bold)
    font.setPixelSize(int(size * 0.62))
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(QRectF(0, 0, size, size * 0.98), Qt.AlignmentFlag.AlignCenter, "N")
    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    data = bytes(buffer.data())
    buffer.close()
    return data


def write_ico(path: Path, frames: list[tuple[int, bytes]]) -> None:
    header = struct.pack("<HHH", 0, 1, len(frames))
    directory = b""
    offset = 6 + 16 * len(frames)
    blobs = b""
    for size, data in frames:
        dim = 0 if size >= 256 else size  # 0 means 256 in the ICO format
        directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blobs += data
    path.write_bytes(header + directory + blobs)


def main() -> int:
    QGuiApplication(sys.argv)  # needed before fonts and painting
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frames = [(size, png_bytes(render(size))) for size in SIZES]
    write_ico(OUT_DIR / "nolde.ico", frames)
    render(256).save(str(OUT_DIR / "nolde.png"), "PNG")
    print(f"wrote {OUT_DIR / 'nolde.ico'} with sizes {', '.join(str(s) for s in SIZES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
