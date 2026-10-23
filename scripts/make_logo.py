"""Render nolde_launcher/ui/assets/images/logo.png: the 'Nolde Launcher' wordmark.

Uses the bundled Space Grotesk Bold font so the logo matches the interface.
Run from the project root:  python scripts/make_logo.py
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QGuiApplication, QImage, QPainter

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "nolde_launcher/ui/assets/fonts/SpaceGrotesk-Bold.ttf"
OUT = ROOT / "nolde_launcher/ui/assets/images/logo.png"


def main() -> int:
    QGuiApplication(sys.argv)  # required before any Qt font or painting call
    font_id = QFontDatabase.addApplicationFont(str(FONT))
    families = QFontDatabase.applicationFontFamilies(font_id)
    if font_id < 0 or not families:
        print("could not load Space Grotesk", file=sys.stderr)
        return 1
    font = QFont(families[0], 44)
    font.setWeight(QFont.Weight.Bold)
    metrics = QFontMetrics(font)
    text = "Nolde Launcher"
    padding = 24
    width = metrics.horizontalAdvance(text) + padding * 2 + 16
    height = metrics.height() + padding * 2

    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setFont(font)
    # "Nolde" in white, "Launcher" in the accent blue.
    x = padding
    base = padding + metrics.ascent()
    painter.setPen(QColor("#e7edf7"))
    painter.drawText(x, base, "Nolde ")
    x += metrics.horizontalAdvance("Nolde ")
    painter.setPen(QColor("#4f86f7"))
    painter.drawText(x, base, "Launcher")
    painter.end()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(OUT), "PNG"):
        print("could not write logo", file=sys.stderr)
        return 1
    print(f"wrote {OUT} ({width}x{height})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
