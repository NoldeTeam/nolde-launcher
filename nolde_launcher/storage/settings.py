"""User settings: folders, catalog appearance, performance, updates and diagnostics.

Every value is validated on load and on update. A corrupt or out-of-range value falls
back to its default, and an invalid update keeps the current value.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from .json_store import JsonStore
from .paths import default_download_dir, default_library_dir, user_data_dir

SETTINGS_SCHEMA_VERSION = 3

GRID_ART = ("cover_logo", "cover", "logo", "text")
CARD_SIZES = ("small", "medium", "large")
MOTION_LEVELS = ("full", "reduced", "off")
IMAGE_CACHE_CHOICES = (20, 60, 120, 240)
DISK_CACHE_CHOICES = (100, 250, 500, 1000, 2000)
CONCURRENT_CHOICES = (1, 2, 3)
SORT_CHOICES = ("name", "updated", "progress")

_CHOICES = {
    "grid_art": GRID_ART,
    "card_size": CARD_SIZES,
    "motion_level": MOTION_LEVELS,
    "image_cache_size": IMAGE_CACHE_CHOICES,
    "disk_cache_mb": DISK_CACHE_CHOICES,
    "max_concurrent_downloads": CONCURRENT_CHOICES,
    "discover_sort": SORT_CHOICES,
}
_BOOLS = {"show_card_details", "load_images", "refresh_catalog_on_start", "check_updates_on_start",
          "notifications", "check_launcher_updates", "welcome_seen"}
_PATHS = {"library_dir", "download_dir"}


def default_motion_level() -> str:
    """Modest machines (4 cores or fewer) start with reduced motion: fewer effects, same feel."""
    return "reduced" if (os.cpu_count() or 2) <= 4 else "full"


@dataclass
class Settings:
    library_dir: str
    download_dir: str
    grid_art: str = "cover_logo"            # cards show: cover_logo | cover | logo | text
    card_size: str = "medium"               # small | medium | large
    show_card_details: bool = True          # description, badges and platform tags on cards
    motion_level: str = "full"              # full | reduced | off
    load_images: bool = True                # when off, no artwork is downloaded or drawn
    image_cache_size: int = 60              # artwork kept in memory (least recently used goes first)
    disk_cache_mb: int = 500                # artwork kept on disk; oldest files are removed first
    refresh_catalog_on_start: bool = True   # when off, start from the saved catalog
    max_concurrent_downloads: int = 2
    discover_sort: str = "name"             # name | updated | progress
    check_updates_on_start: bool = True     # look for new versions of installed games
    notifications: bool = True              # Windows notifications when work finishes
    check_launcher_updates: bool = True     # look for a newer launcher on GitHub at startup
    welcome_seen: bool = False              # the Early Access welcome has been shown once

    @classmethod
    def defaults(cls) -> "Settings":
        return cls(library_dir=str(default_library_dir()),
                   download_dir=str(default_download_dir()),
                   motion_level=default_motion_level())


def _valid(name: str, value: Any, default: Any) -> Any:
    if name in _PATHS:
        return value if isinstance(value, str) and value else default
    if name in _BOOLS:
        return value if isinstance(value, bool) else default
    if name in _CHOICES:
        return value if value in _CHOICES[name] else default
    return default


def _migrate(raw: dict[str, Any]) -> dict[str, Any]:
    """Older files had two switches. Map them onto the single motion level."""
    if "motion_level" not in raw:
        if raw.get("animations") is False:
            raw["motion_level"] = "off"
        elif raw.get("hover_effects") is False:
            raw["motion_level"] = "reduced"
    return raw


class SettingsService:
    def __init__(self, path: Path | None = None) -> None:
        path = path or user_data_dir() / "settings.json"
        self._store = JsonStore(path, SETTINGS_SCHEMA_VERSION, lambda: {})
        self.settings = self._load()

    def _read_any_version(self) -> dict[str, Any]:
        """Read the file whatever its schema version, so older settings are migrated
        instead of being discarded. Only a corrupt file is set aside."""
        path = self._store.path
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            self._store._quarantine_corrupt_file()
            return {}
        return data if isinstance(data, dict) else {}

    def _load(self) -> Settings:
        raw = _migrate(self._read_any_version())
        defaults = Settings.defaults()
        values = {}
        for f in fields(Settings):
            default = getattr(defaults, f.name)
            values[f.name] = _valid(f.name, raw.get(f.name, default), default)
        return Settings(**values)

    def save(self) -> None:
        self._store.save(asdict(self.settings))

    def update(self, **changes: Any) -> None:
        """Validate and apply several settings at once, then save."""
        known = {f.name for f in fields(Settings)}
        for name, value in changes.items():
            if name not in known:
                raise KeyError(f"unknown setting: {name}")
            current = getattr(self.settings, name)
            setattr(self.settings, name, _valid(name, value, current))  # invalid keeps current
        self.save()

    @property
    def library_dir(self) -> Path:
        return Path(self.settings.library_dir)

    @property
    def download_dir(self) -> Path:
        return Path(self.settings.download_dir)

    def set_library_dir(self, path: Path) -> None:
        self.update(library_dir=str(Path(path).expanduser().resolve()))

    def set_download_dir(self, path: Path) -> None:
        self.update(download_dir=str(Path(path).expanduser().resolve()))
