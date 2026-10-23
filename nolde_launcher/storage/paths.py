"""Locations for user data. Never depends on the current working directory."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "NoldeLauncher"
DATA_DIR_ENV = "NOLDE_DATA_DIR"  # override, mainly for tests and portable installs


def user_data_dir() -> Path:
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        path = Path(override).expanduser().resolve()
    elif sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        path = Path(base) / APP_DIR_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_library_dir() -> Path:
    return user_data_dir() / "Library"


def default_download_dir() -> Path:
    return user_data_dir() / "Downloads"


def cache_dir() -> Path:
    path = user_data_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = user_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path
