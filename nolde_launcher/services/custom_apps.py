"""Apps the user adds to the launcher themselves.

A custom app becomes a normal project: it appears in Discover, has a project page, and is
installed and launched through the same code as catalog projects. What differs is where its
details come from (this file) and a few extra steps after installation (files and mods).

Two management modes:
- managed: the app has a public GitHub repository. Its release is installed, and updates come
  from that repository. The asset filter chooses which release file is the build.
- manual:  the launcher does not download anything. The user puts the files in the app's folder
  inside the library and registers the executable.

Everything the user types is validated here before it is saved or used.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from urllib.parse import urlparse

from ..models.project import CatalogProject
from ..storage.json_store import JsonStore
from .install_manager import InstallError, is_safe_folder_name, resolve_inside
from .release_service import parse_github_repo

STORE_VERSION = 1
MANAGEMENT = ("managed", "manual")
MAX_TAGS = 8
MAX_MODS = 20


class CustomAppError(ValueError):
    """The user's input is not usable. The message is shown in the form."""


@dataclass
class CustomAppSpec:
    name: str                               # project name (required)
    id: str = ""                            # assigned on creation: custom-<hex>
    author: str = ""
    display_name: str = ""                  # shown in the launcher; defaults to the name
    management: str = "manual"              # managed | manual
    repository_url: str = ""                # required when managed; a GitHub repository
    asset_filter: str = "*.zip"            # glob for the release file, managed only
    folder_name: str = ""                   # folder inside the library; defaults to the name
    tags: list[str] = field(default_factory=list)
    icon_url: str = ""                      # https image
    files_to_add: list[str] = field(default_factory=list)   # local files copied after install
    mods_path: str = ""                     # folder inside the game folder where mods go
    mod_sources: list[str] = field(default_factory=list)    # GitHub repositories of mods
    mods_own_folder: bool = True            # each mod goes into its own folder

    def to_project(self) -> CatalogProject:
        slug = self.folder_name or self.name
        return CatalogProject(
            id=self.id,
            game_title=self.display_name or self.name,
            project_name=self.name,
            slug=slug,
            description="",
            long_description="",
            project_types=("custom",),
            status="available",
            platforms=("Windows",),
            tags=tuple(self.tags),
            authors=(self.author,) if self.author else (),
            cover_url=self.icon_url,
            repository_url=self.repository_url if self.management == "managed" else "",
            custom=True,
            management=self.management,
            asset_filter=self.asset_filter if self.management == "managed" else "",
            files_to_add=tuple(self.files_to_add),
            mods_path=self.mods_path,
            mod_sources=tuple(self.mod_sources),
            mods_own_folder=self.mods_own_folder,
        )


# ----- validation -----

def _clean_list(values) -> list[str]:
    return [str(v).strip() for v in (values or []) if str(v).strip()]


def validate(spec: CustomAppSpec) -> CustomAppSpec:
    """Check and tidy the user's input. Returns the spec with clean values, or raises."""
    spec.name = spec.name.strip()
    if not spec.name or len(spec.name) > 120:
        raise CustomAppError("Enter a name (up to 120 characters).")
    spec.author = spec.author.strip()[:120]
    spec.display_name = spec.display_name.strip()[:120]
    if spec.management not in MANAGEMENT:
        raise CustomAppError("Choose how the app is managed.")

    spec.tags = _clean_list(spec.tags)
    if len(spec.tags) > MAX_TAGS or any(len(t) > 30 for t in spec.tags):
        raise CustomAppError(f"Use up to {MAX_TAGS} tags, each up to 30 characters.")

    spec.folder_name = spec.folder_name.strip() or spec.name
    if not is_safe_folder_name(spec.folder_name):
        raise CustomAppError("The folder name may use letters, numbers, spaces, dots, dashes and underscores.")

    spec.icon_url = spec.icon_url.strip()
    if spec.icon_url and urlparse(spec.icon_url).scheme != "https":
        raise CustomAppError("The icon must be an https:// address.")

    spec.files_to_add = _clean_list(spec.files_to_add)
    for path in spec.files_to_add:
        if not Path(path).is_file():
            raise CustomAppError(f"File not found: {path}")

    spec.mod_sources = _clean_list(spec.mod_sources)
    if len(spec.mod_sources) > MAX_MODS:
        raise CustomAppError(f"Use at most {MAX_MODS} mod sources.")
    for url in spec.mod_sources:
        if parse_github_repo(url) is None:
            raise CustomAppError(f"Mod source must be a GitHub repository: {url}")

    raw_mods = spec.mods_path.strip().replace("\\", "/")
    if raw_mods.startswith("/") or re.match(r"^[A-Za-z]:", raw_mods):
        raise CustomAppError("The mods folder must be a relative folder inside the game.")
    spec.mods_path = raw_mods.strip("/")
    if spec.mods_path:
        try:
            resolve_inside(Path("/"), spec.mods_path)  # rejects ".." segments
        except InstallError as exc:
            raise CustomAppError("The mods folder must be a relative folder inside the game.") from exc
    if spec.mod_sources and not spec.mods_path:
        raise CustomAppError("Choose a mods folder when you add mod sources.")

    if spec.management == "managed":
        if parse_github_repo(spec.repository_url.strip()) is None:
            raise CustomAppError("A managed app needs a public GitHub repository, for example https://github.com/owner/repo.")
        spec.repository_url = spec.repository_url.strip()
        spec.asset_filter = spec.asset_filter.strip() or "*.zip"
        if not spec.asset_filter or "/" in spec.asset_filter or "\\" in spec.asset_filter:
            raise CustomAppError("The release file filter is a file name pattern, for example *Windows*.zip.")
    else:
        if spec.repository_url.strip():
            raise CustomAppError("A manual app has no repository. Choose 'managed' to use one.")
        spec.repository_url = ""
        spec.asset_filter = ""
        spec.files_to_add = []
    return spec


# ----- storage -----

class CustomAppStore:
    def __init__(self, path: Path) -> None:
        self._store = JsonStore(path, STORE_VERSION, lambda: {"apps": []})

    def list(self) -> list[CustomAppSpec]:
        known = {f.name for f in fields(CustomAppSpec)}
        apps = []
        for raw in self._store.load().get("apps", []):
            if not isinstance(raw, dict) or not raw.get("id"):
                continue
            apps.append(CustomAppSpec(**{k: v for k, v in raw.items() if k in known}))
        return apps

    def get(self, app_id: str) -> CustomAppSpec | None:
        return next((a for a in self.list() if a.id == app_id), None)

    def _save(self, apps: list[CustomAppSpec]) -> None:
        self._store.save({"apps": [asdict(a) for a in apps]})

    def add(self, spec: CustomAppSpec) -> CustomAppSpec:
        spec = validate(spec)
        spec.id = "custom-" + secrets.token_hex(6)
        apps = self.list()
        apps.append(spec)
        self._save(apps)
        return spec

    def update(self, app_id: str, spec: CustomAppSpec) -> CustomAppSpec:
        spec = validate(spec)
        spec.id = app_id
        apps = [spec if a.id == app_id else a for a in self.list()]
        self._save(apps)
        return spec

    def remove(self, app_id: str) -> None:
        self._save([a for a in self.list() if a.id != app_id])
