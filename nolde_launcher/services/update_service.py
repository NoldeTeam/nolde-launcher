"""Updates, in two parts.

1. Game updates: compare each installed game's version with the newest release of its
   verified source. Reads only; nothing is downloaded or installed here.

2. Launcher updates: read a signed-off manifest from an official URL, verify the package
   hash, and save the verified package. Installing it is left to the user. Replacing a
   running program safely needs code signing and an installer, which are not in place yet.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from ..app.version import __version__
from .download_manager import DownloadError, download_to_file
from .source_resolver import PrimaryAction

HEX64 = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_PACKAGE_HOSTS = {"github.com", "objects.githubusercontent.com",
                         "release-assets.githubusercontent.com"}


# ----- game updates -----

def check_game_updates(records, project_for, resolver) -> dict[str, str]:
    """Return {project_id: newer_tag} for installed games that have a newer verified build."""
    found: dict[str, str] = {}
    for record in records:
        project = project_for(record.project_id)
        if project is None or not project.repository_url:
            continue
        availability = resolver.resolve(project)
        if availability.action is not PrimaryAction.INSTALL or availability.build is None:
            continue
        tag = availability.build.release.tag
        if tag and tag != record.installed_version:
            found[record.project_id] = tag
    return found


# ----- launcher updates -----

class LauncherUpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class LauncherManifest:
    version: str
    url: str
    sha256: str
    notes: str = ""


def parse_version(text: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", text)
    if not parts:
        raise LauncherUpdateError("version is not numeric")
    return tuple(int(p) for p in parts[:4])


def parse_manifest(payload: bytes | str) -> LauncherManifest:
    """Strict validation: HTTPS only, allow-listed host, 64-hex SHA-256."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise LauncherUpdateError("update manifest is not valid JSON") from exc
    if not isinstance(data, dict):
        raise LauncherUpdateError("update manifest must be an object")
    version = str(data.get("version", "")).strip()
    url = str(data.get("url", "")).strip()
    sha = str(data.get("sha256", "")).strip().lower()
    parse_version(version)
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "") not in ALLOWED_PACKAGE_HOSTS:
        raise LauncherUpdateError("update package is not on an allowed HTTPS host")
    if not HEX64.match(sha):
        raise LauncherUpdateError("update manifest has no valid SHA-256")
    return LauncherManifest(version, url, sha, str(data.get("notes", ""))[:2000])


def is_newer(candidate: str, current: str = __version__) -> bool:
    return parse_version(candidate) > parse_version(current)


def fetch_manifest(url: str, http_get) -> LauncherManifest:
    if not url:
        raise LauncherUpdateError("no update source is configured yet")
    if urlparse(url).scheme != "https":
        raise LauncherUpdateError("the update source must use HTTPS")
    response = http_get(url, timeout=(10, 20), headers={"Accept": "application/json",
                                                        "User-Agent": "NoldeLauncher/0.1"})
    if response.status_code != 200:
        raise LauncherUpdateError(f"update source returned HTTP {response.status_code}")
    return parse_manifest(response.content)


def download_launcher_package(manifest: LauncherManifest, target_dir: Path, session=None) -> Path:
    """Download the package and verify its SHA-256. Anything that fails verification is deleted."""
    target_dir.mkdir(parents=True, exist_ok=True)
    name = Path(urlparse(manifest.url).path).name or f"NoldeLauncher-{manifest.version}.zip"
    dest = target_dir / re.sub(r"[^A-Za-z0-9._-]", "_", name)
    try:
        return download_to_file(manifest.url, dest, session=session,
                                expected_sha256=manifest.sha256)
    except DownloadError as exc:
        raise LauncherUpdateError(f"download could not be verified: {exc}") from exc
