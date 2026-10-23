"""Motion levels, chosen in Settings.

full     page transitions, card fades, hover lift, navigation indicator
reduced  page transitions and the navigation indicator only
off      no animation at all
"""

from __future__ import annotations

LEVELS = ("full", "reduced", "off")
_level = {"value": "full"}
_scrolling = {"value": False}


def configure(level: str) -> None:
    _level["value"] = level if level in LEVELS else "full"


def level() -> str:
    return _level["value"]


def animations_enabled() -> bool:
    """Page transitions and the navigation indicator."""
    return _level["value"] != "off"


def card_motion_enabled() -> bool:
    """Per-card effects. Only in full mode, because each one costs a redraw."""
    return _level["value"] == "full"


def set_scrolling(active: bool) -> None:
    """True while a grid is being scrolled. Cards passing under a still pointer must not
    lift, or every card that scrolls past would start and stop a shadow animation."""
    _scrolling["value"] = bool(active)


def is_scrolling() -> bool:
    return _scrolling["value"]


def hover_enabled() -> bool:
    return _level["value"] == "full" and not _scrolling["value"]
