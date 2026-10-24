"""Internal model for a Nolde catalog entry.

The public catalog is the discovery source only. Nothing here implies that a
build can be downloaded or installed; that is decided by the download-source
resolver. Missing fields stay empty rather than being invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


class CatalogSchemaError(ValueError):
    """Raised when a catalog entry lacks the fields needed to identify it."""


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _texts(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(t for t in (_text(v) for v in value) if t)


def _https_url(value: Any) -> str:
    """Accept only well-formed HTTPS URLs; anything else becomes empty."""
    text = _text(value)
    if not text:
        return ""
    parsed = urlparse(text)
    return text if parsed.scheme == "https" and parsed.netloc else ""


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, min(100, int(value)))


@dataclass(frozen=True)
class RelatedLink:
    label: str
    url: str


@dataclass(frozen=True)
class CatalogProject:
    id: str
    game_title: str
    project_name: str
    slug: str = ""
    description: str = ""
    long_description: str = ""
    project_types: tuple[str, ...] = ()
    status: str = ""
    platforms: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    authors: tuple[str, ...] = ()
    cover_url: str = ""
    logo_url: str = ""
    repository_url: str = ""
    releases_url: str = ""
    official_url: str = ""
    documentation_url: str = ""
    discord_url: str = ""
    related_links: tuple[RelatedLink, ...] = ()
    requires_original_assets: str = ""
    last_updated: str = ""
    progress: int | None = None
    made_with_ai: bool = False
    sources: tuple[str, ...] = field(default_factory=tuple)
    # Fields for apps the user adds (see services/custom_apps.py). Catalog projects leave them empty.
    custom: bool = False
    management: str = "catalog"          # catalog | managed | manual
    asset_filter: str = ""               # glob for the release file (managed custom apps)
    files_to_add: tuple[str, ...] = ()   # local files copied into the game folder after install
    mods_path: str = ""                  # folder inside the game folder for mods
    mod_sources: tuple[str, ...] = ()    # GitHub repositories of mods
    mods_own_folder: bool = True         # True: each mod gets its own folder

    @property
    def search_text(self) -> str:
        return f"{self.game_title} {self.project_name}".casefold()

    @property
    def project_page_url(self) -> str:
        """Best official or documentary page, if one exists."""
        return self.official_url or self.documentation_url or self.repository_url

    @classmethod
    def from_dict(cls, raw: Any) -> "CatalogProject":
        if not isinstance(raw, dict):
            raise CatalogSchemaError("entry is not an object")
        project_id = _text(raw.get("id"))
        game_title = _text(raw.get("gameTitle"))
        project_name = _text(raw.get("projectName"))
        if not project_id or not game_title or not project_name:
            raise CatalogSchemaError("entry is missing id, gameTitle or projectName")

        related = []
        for item in raw.get("relatedLinks") or []:
            if isinstance(item, dict):
                url = _https_url(item.get("url"))
                if url:
                    related.append(RelatedLink(label=_text(item.get("label")) or url, url=url))

        last_updated = _text(raw.get("lastUpdated"))
        return cls(
            id=project_id,
            game_title=game_title,
            project_name=project_name,
            slug=_text(raw.get("slug")),
            description=_text(raw.get("description")),
            long_description=_text(raw.get("longDescription")),
            project_types=_texts(raw.get("type")),
            status=_text(raw.get("status")).casefold(),
            platforms=_texts(raw.get("platforms")),
            tags=_texts(raw.get("tags")),
            authors=_texts(raw.get("authors")),
            cover_url=_https_url(raw.get("cover")),
            logo_url=_https_url(raw.get("logo")),
            repository_url=_https_url(raw.get("repositoryUrl")),
            releases_url=_https_url(raw.get("releasesUrl")),
            official_url=_https_url(raw.get("officialUrl")),
            documentation_url=_https_url(raw.get("documentationUrl")),
            discord_url=_https_url(raw.get("discordUrl")),
            related_links=tuple(related),
            requires_original_assets=_text(raw.get("requiresOriginalAssets")).casefold(),
            last_updated=last_updated,
            progress=_optional_int(raw.get("progress")),
            made_with_ai=raw.get("madeWithAi") is True,
            sources=tuple(u for u in (_https_url(s) for s in raw.get("sources") or []) if u),
        )
