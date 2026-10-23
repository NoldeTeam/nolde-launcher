"""Remote Nolde catalog: fetch, validate, cache, search and filter.

The launcher never writes to the remote catalog. Cached data is used when the
network is unavailable, and every snapshot records whether it came from the
network or from the cache so the UI can say so honestly.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

import requests

from ..app.version import NOLDE_CATALOG_URL
from ..models.project import CatalogProject, CatalogSchemaError
from ..storage.json_store import JsonStore

MAX_CATALOG_BYTES = 5 * 1024 * 1024
REQUEST_TIMEOUT = (10, 20)
CACHE_SCHEMA_VERSION = 1


class CatalogError(RuntimeError):
    """The catalog could not be loaded from the network or the cache."""


@dataclass(frozen=True)
class CatalogSnapshot:
    projects: tuple[CatalogProject, ...]
    source: str  # "network" or "cache"
    fetched_at: float  # Unix time of the network fetch that produced the data
    skipped_entries: int = 0


def parse_catalog(payload: str | bytes) -> tuple[list[CatalogProject], int]:
    """Parse the catalog JSON array. Invalid entries are skipped and counted."""
    if isinstance(payload, bytes):
        if len(payload) > MAX_CATALOG_BYTES:
            raise CatalogError("catalog response is larger than the allowed size")
        payload = payload.decode("utf-8")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise CatalogError(f"catalog is not valid JSON: {exc.msg}") from exc
    if not isinstance(data, list):
        raise CatalogError("catalog root must be a JSON array")

    projects: list[CatalogProject] = []
    seen: set[str] = set()
    skipped = 0
    for raw in data:
        try:
            project = CatalogProject.from_dict(raw)
        except CatalogSchemaError:
            skipped += 1
            continue
        if project.id in seen:
            skipped += 1
            continue
        seen.add(project.id)
        projects.append(project)

    if data and not projects:
        raise CatalogError("catalog contains no usable entries")
    return projects, skipped


def filter_projects(
    projects: Iterable[CatalogProject],
    query: str = "",
    project_type: str = "",
    status: str = "",
    platform: str = "",
) -> list[CatalogProject]:
    """Filter by title or project name, type, status and platform.

    Empty filter values mean "no restriction". Comparisons are case-insensitive.
    """
    needle = query.strip().casefold()
    wanted_type = project_type.casefold()
    wanted_status = status.casefold()
    wanted_platform = platform.casefold()
    result = []
    for project in projects:
        if needle and needle not in project.search_text:
            continue
        if wanted_type and wanted_type not in {t.casefold() for t in project.project_types}:
            continue
        if wanted_status and project.status != wanted_status:
            continue
        if wanted_platform and wanted_platform not in {p.casefold() for p in project.platforms}:
            continue
        result.append(project)
    return result


def distinct_values(projects: Sequence[CatalogProject], attr: str) -> list[str]:
    values: set[str] = set()
    for project in projects:
        items = getattr(project, attr)
        if isinstance(items, str):
            items = (items,) if items else ()
        values.update(v for v in items if v)
    return sorted(values, key=str.casefold)


class CatalogService:
    def __init__(self, cache_store: JsonStore,
                 url: str = NOLDE_CATALOG_URL,
                 http_get: Callable[..., requests.Response] | None = None) -> None:
        if not url.startswith("https://"):
            raise ValueError("catalog URL must use HTTPS")
        self._cache = cache_store
        self._url = url
        self._get = http_get or requests.get

    def refresh(self) -> CatalogSnapshot:
        """Fetch from the network and update the cache. Raises CatalogError."""
        try:
            response = self._get(
                self._url,
                timeout=REQUEST_TIMEOUT,
                headers={"Accept": "application/json",
                         "User-Agent": "NoldeLauncher/0.1"},
                stream=False,
            )
        except requests.RequestException as exc:
            raise CatalogError(f"network error: {exc.__class__.__name__}") from exc
        if response.status_code != 200:
            raise CatalogError(f"catalog server returned HTTP {response.status_code}")
        body = response.content
        projects, skipped = parse_catalog(body)
        fetched_at = time.time()
        self._cache.save({
            "fetched_at": fetched_at,
            "raw": json.loads(body.decode("utf-8")),
        })
        return CatalogSnapshot(tuple(projects), "network", fetched_at, skipped)

    def load_cached(self) -> CatalogSnapshot | None:
        data = self._cache.load()
        raw = data.get("raw")
        if raw is None:
            return None
        try:
            projects, skipped = parse_catalog(json.dumps(raw))
        except CatalogError:
            return None
        fetched = data.get("fetched_at")
        return CatalogSnapshot(tuple(projects), "cache",
                               float(fetched) if isinstance(fetched, (int, float)) else 0.0,
                               skipped)


def make_cache_store(path) -> JsonStore:
    return JsonStore(path, CACHE_SCHEMA_VERSION, lambda: {})
