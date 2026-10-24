"""Updates, in two parts.

1. Game updates: compare each installed game's version with the newest release of its
   verified source. Reads only; nothing is downloaded or installed here.

2. Launcher updates: read the latest public release of the launcher from GitHub, pick the
   Windows installer, check its SHA-256, and download it. The launcher installs it only after
   the user agrees. Installing uses the installer's silent mode, which upgrades in place.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

from ..app.version import LATEST_RELEASE_API, __version__
from .download_manager import DownloadError, download_to_file
from .source_resolver import PrimaryAction

HEX64 = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_PACKAGE_HOSTS = {"github.com", "objects.githubusercontent.com",
                         "release-assets.githubusercontent.com"}
INSTALLER_NAME = re.compile(r"^NoldeLauncher-Setup-(\d+(?:\.\d+){1,3})\.exe$")
RELEASE_TIMEOUT = (10, 20)


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
class LauncherRelease:
    version: str
    installer_url: str
    sha256: str
    page_url: str
    notes: str = ""


def parse_version(text: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", text)
    if not parts:
        raise LauncherUpdateError("version is not numeric")
    return tuple(int(p) for p in parts[:4])


def is_newer(candidate: str, current: str = __version__) -> bool:
    return parse_version(candidate) > parse_version(current)


def is_installed_build() -> bool:
    """True when running the packaged launcher. Updates are installed only from a packaged build;
    when running from source, the launcher only reports that a newer version exists."""
    return bool(getattr(sys, "frozen", False))


def select_installer(release: dict, http_get) -> LauncherRelease:
    """Choose the Windows installer of a GitHub release and its SHA-256.
    Refuses anything that is not a published, matching, HTTPS installer with a known hash."""
    if release.get("draft") or release.get("prerelease"):
        raise LauncherUpdateError("the latest release is not a published stable release")
    tag = str(release.get("tag_name") or "").strip()
    version = tag[1:] if tag[:1] in ("v", "V") else tag
    parse_version(version)  # raises when the tag is not a version

    assets = release.get("assets") or []
    installer = None
    for asset in assets:
        match = INSTALLER_NAME.match(str(asset.get("name") or ""))
        if match and match.group(1) == version:
            installer = asset
            break
    if installer is None:
        raise LauncherUpdateError("the release has no Windows installer for this version")

    url = str(installer.get("browser_download_url") or "")
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "") not in ALLOWED_PACKAGE_HOSTS:
        raise LauncherUpdateError("the installer is not on an allowed HTTPS host")

    sha = ""
    digest = str(installer.get("digest") or "")
    if digest.startswith("sha256:"):
        sha = digest.split(":", 1)[1].strip().lower()
    if not HEX64.match(sha):
        sha = _sha_from_companion_file(assets, installer, http_get)
    if not HEX64.match(sha):
        raise LauncherUpdateError("the release does not publish a SHA-256 for its installer")

    return LauncherRelease(version=version, installer_url=url, sha256=sha,
                           page_url=str(release.get("html_url") or ""),
                           notes=str(release.get("body") or "")[:2000])


def _sha_from_companion_file(assets, installer, http_get) -> str:
    """Fallback for releases whose API has no digest: a '<installer>.sha256' file next to it."""
    wanted = str(installer.get("name")) + ".sha256"
    for asset in assets:
        if asset.get("name") == wanted and urlparse(str(asset.get("browser_download_url"))).scheme == "https":
            response = http_get(asset["browser_download_url"], timeout=RELEASE_TIMEOUT)
            if response.status_code == 200:
                words = response.content.decode("utf-8", "replace").split()
                return words[0].lower() if words else ""
    return ""


def check_latest_release(http_get=requests.get, current: str = __version__) -> LauncherRelease | None:
    """Return the newer release, or None when this version is current or no release exists yet."""
    response = http_get(LATEST_RELEASE_API, timeout=RELEASE_TIMEOUT,
                        headers={"Accept": "application/vnd.github+json",
                                 "X-GitHub-Api-Version": "2022-11-28",
                                 "User-Agent": "NoldeLauncher"})
    if response.status_code == 404:
        return None  # no published release yet
    if response.status_code in (403, 429):
        raise LauncherUpdateError("GitHub is limiting requests; try again later")
    if response.status_code != 200:
        raise LauncherUpdateError(f"GitHub returned HTTP {response.status_code}")
    try:
        release = json.loads(response.content)
    except (ValueError, TypeError) as exc:
        raise LauncherUpdateError("GitHub returned an unreadable release") from exc
    if not isinstance(release, dict):
        raise LauncherUpdateError("unexpected release format")
    chosen = select_installer(release, http_get)
    return chosen if is_newer(chosen.version, current) else None


def download_installer(release: LauncherRelease, target_dir: Path, session=None) -> Path:
    """Download the installer and verify its SHA-256. A file that fails is deleted."""
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / f"NoldeLauncher-Setup-{release.version}.exe"
    try:
        return download_to_file(release.installer_url, dest, session=session,
                                expected_sha256=release.sha256)
    except DownloadError as exc:
        raise LauncherUpdateError(f"download could not be verified: {exc}") from exc


def installer_arguments(installer: Path) -> list[str]:
    """Silent, in-place upgrade. The old launcher is closed first and restarted afterwards."""
    return [str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
            "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"]
