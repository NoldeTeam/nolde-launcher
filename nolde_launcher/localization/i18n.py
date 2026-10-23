"""Translation lookup. Interface text is referenced by key, never hardcoded.

Only English ships in the first release. Future languages add `<code>.json`
files next to en.json; the language selector is intentionally not shown until
at least one additional language exists.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_LOCALE_DIR = Path(__file__).resolve().parent
DEFAULT_LOCALE = "en"
_catalog: dict[str, str] = {}
_fallback: dict[str, str] = {}


def _load(locale: str) -> dict[str, str]:
    path = _LOCALE_DIR / f"{locale}.json"
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return {str(k): str(v) for k, v in data.items() if not str(k).startswith("_")}


def set_locale(locale: str = DEFAULT_LOCALE) -> None:
    global _catalog, _fallback
    _fallback = _load(DEFAULT_LOCALE)
    _catalog = _load(locale) if locale != DEFAULT_LOCALE else dict(_fallback)


def available_locales() -> list[str]:
    return sorted(p.stem for p in _LOCALE_DIR.glob("*.json"))


def t(key: str, **kwargs: Any) -> str:
    """Return translated text. Missing keys fall back to English, then to the key."""
    if not _fallback:
        set_locale()
    template = _catalog.get(key) or _fallback.get(key) or key
    try:
        return template.format(**kwargs) if kwargs else template
    except (KeyError, IndexError, ValueError):
        return template
