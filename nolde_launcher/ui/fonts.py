"""Load the bundled Inter and Space Grotesk fonts into the application font database."""

from __future__ import annotations

from PySide6.QtGui import QFontDatabase

from .theme import FONT_DIR

_loaded: list[str] | None = None


def load_fonts() -> list[str]:
    """Register every bundled .ttf once. Returns the family names that loaded."""
    global _loaded
    if _loaded is not None:
        return _loaded
    families: set[str] = set()
    for path in sorted(FONT_DIR.glob("*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            families.update(QFontDatabase.applicationFontFamilies(font_id))
    _loaded = sorted(families)
    return _loaded
