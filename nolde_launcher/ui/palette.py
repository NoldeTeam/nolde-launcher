"""User colour themes: a primary colour (backgrounds) and a secondary colour (buttons, lines).

The default palette is the built-in one. When the user picks colours, every other colour in the
theme is derived from those two, so text stays readable and the surfaces stay in one family.
Applying a palette changes the shared COLORS dict in place, and the stylesheet is then rebuilt.
"""

from __future__ import annotations

import re

from .theme import COLORS

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
DEFAULT = dict(COLORS)  # snapshot of the built-in palette, taken before any change
DEFAULT_PRIMARY = DEFAULT["bg"]
DEFAULT_SECONDARY = DEFAULT["accent"]
# Colours that are not part of the theme and stay the same in every palette.
FIXED_KEYS = ("play", "play_hover", "success", "warning", "danger")


def valid_hex(value: str) -> bool:
    return isinstance(value, str) and bool(HEX.match(value))


def _rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def mix(a: str, b: str, t: float) -> str:
    """Colour a, moved t of the way toward colour b (t = 0 is a, t = 1 is b)."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(x + (y - x) * t for x, y in zip(ra, rb)))


def luminance(color: str) -> float:
    r, g, b = (c / 255 for c in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def derive(primary: str, secondary: str, text: str = "") -> dict[str, str]:
    """All theme colours, from the colours the user chose. `text` is optional: when it is empty the
    text colour is picked for good contrast on the primary colour."""
    dark = luminance(primary) < 0.5
    if not text:
        text = "#e9edf5" if dark else "#1b1f27"
    lift = "#ffffff" if dark else "#000000"  # surfaces step lighter on dark themes, darker on light
    on_accent = "#ffffff" if luminance(secondary) < 0.6 else "#14171f"
    return {
        "on_accent": on_accent,
        "bg": primary,
        "sidebar": primary,
        "panel": mix(primary, lift, 0.035),
        "card": mix(primary, lift, 0.06),
        "card_hover": mix(primary, lift, 0.10),
        "border": mix(primary, secondary, 0.42),  # lines take the secondary colour
        "text": text,
        "muted": mix(text, primary, 0.45),
        "subtle": mix(text, primary, 0.65),
        "accent": secondary,
        "accent_hover": mix(secondary, "#ffffff", 0.12),
        "accent_pressed": mix(secondary, "#000000", 0.14),
    }


def apply_palette(primary: str = "", secondary: str = "", text: str = "") -> None:
    """Use the user's colours, or the built-in ones when all are empty. Raises ValueError when a
    colour is not a #RRGGBB value."""
    if not primary and not secondary and not text:
        COLORS.update(DEFAULT)
        return
    primary = primary or DEFAULT_PRIMARY
    secondary = secondary or DEFAULT_SECONDARY
    if not (valid_hex(primary) and valid_hex(secondary) and (not text or valid_hex(text))):
        raise ValueError("colours must be #RRGGBB")
    COLORS.update(derive(primary, secondary, text))
    for key in FIXED_KEYS:
        COLORS[key] = DEFAULT[key]
