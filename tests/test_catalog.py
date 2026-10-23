import json

import pytest
import requests

from nolde_launcher.models.project import CatalogProject, CatalogSchemaError
from nolde_launcher.services.catalog_service import (
    CatalogError, CatalogService, distinct_values, filter_projects, make_cache_store, parse_catalog,
)
from tests.helpers import FakeResponse

REAL_STYLE_ENTRY = {
    "id": "banjo-recomp", "gameTitle": "Banjo-Kazooie", "projectName": "Banjo: Recompiled",
    "slug": "banjo-recomp", "description": "A port.", "longDescription": "Long.",
    "type": ["recompilation"], "status": "available", "platforms": ["Windows", "Linux"],
    "tags": ["N64"], "cover": "https://images.example.com/c.png", "logo": "http://insecure/l.png",
    "progress": 0, "repositoryUrl": "https://github.com/BanjoRecomp/BanjoRecomp",
    "releasesUrl": "https://github.com/BanjoRecomp/BanjoRecomp/releases", "officialUrl": "",
    "documentationUrl": "https://github.com/BanjoRecomp/BanjoRecomp/blob/main/README.md",
    "authors": ["Banjo: Recompiled Team"], "relatedLinks": [{"label": "RT64", "url": "https://github.com/rt64/rt64"}, {"label": "bad", "url": "javascript:alert(1)"}],
    "requiresOriginalAssets": "yes", "lastUpdated": "2026-07-31", "madeWithAi": False,
    "sources": ["https://github.com/BanjoRecomp/BanjoRecomp"],
}
GITLAB_ENTRY = {
    "id": "extreme-g-recompiled", "gameTitle": "Extreme-G", "projectName": "Extreme-G: Recompiled",
    "type": ["recompilation"], "status": "available", "platforms": ["Windows"],
    "repositoryUrl": "https://gitlab.com/sonicdcer/ExtremeGRecomp",
    "releasesUrl": "https://gitlab.com/sonicdcer/ExtremeGRecomp/-/releases",
    "progress": None, "lastUpdated": None,
}
MINIMAL_ENTRY = {"id": "bare", "gameTitle": "Bare Game", "projectName": "Bare Project"}


def catalog_text(*entries):
    return json.dumps(list(entries))


def test_real_style_entry_maps_fields_and_drops_unsafe_urls():
    project = CatalogProject.from_dict(REAL_STYLE_ENTRY)
    assert project.project_types == ("recompilation",)
    assert project.cover_url == "https://images.example.com/c.png"
    assert project.logo_url == ""  # http:// is rejected
    assert [link.label for link in project.related_links] == ["RT64"]  # javascript: dropped
    assert project.project_page_url.endswith("/blob/main/README.md")  # official empty -> docs


def test_minimal_entry_gets_safe_defaults_without_fabrication():
    project = CatalogProject.from_dict(MINIMAL_ENTRY)
    assert project.authors == () and project.platforms == ()
    assert project.repository_url == "" and project.progress is None
    assert project.made_with_ai is False
    assert project.project_page_url == ""


@pytest.mark.parametrize("bad", [
    {"gameTitle": "No id", "projectName": "x"},
    {"id": "x", "projectName": "No title"},
    {"id": "", "gameTitle": "a", "projectName": "b"},
    "not an object",
    None,
])
def test_invalid_entries_are_rejected(bad):
    with pytest.raises(CatalogSchemaError):
        CatalogProject.from_dict(bad)


def test_parse_skips_invalid_and_duplicate_entries_and_counts_them():
    projects, skipped = parse_catalog(catalog_text(
        REAL_STYLE_ENTRY, {"id": "broken"}, REAL_STYLE_ENTRY, GITLAB_ENTRY, "junk"))
    assert [p.id for p in projects] == ["banjo-recomp", "extreme-g-recompiled"]
    assert skipped == 3


@pytest.mark.parametrize("payload", ["not json", '{"projects": []}', "[]", catalog_text({"id": "x"})])
def test_malformed_catalogs_raise_catalog_error(payload):
    if payload == "[]":
        projects, skipped = parse_catalog(payload)  # empty but valid array is fine
        assert projects == []
        return
    with pytest.raises(CatalogError):
        parse_catalog(payload)


def test_oversized_response_is_refused():
    with pytest.raises(CatalogError):
        parse_catalog(b"[" + b" " * (5 * 1024 * 1024 + 1) + b"]")


def test_filters_by_title_project_type_status_and_platform():
    projects, _ = parse_catalog(catalog_text(REAL_STYLE_ENTRY, GITLAB_ENTRY))
    assert [p.id for p in filter_projects(projects, query="banjo")] == ["banjo-recomp"]
    assert [p.id for p in filter_projects(projects, query="Extreme-G: rec")] == ["extreme-g-recompiled"]
    assert len(filter_projects(projects, project_type="Recompilation")) == 2
    assert filter_projects(projects, status="archived") == []
    assert [p.id for p in filter_projects(projects, platform="linux")] == ["banjo-recomp"]
    assert distinct_values(projects, "platforms") == ["Linux", "Windows"]


def test_refresh_caches_and_offline_startup_uses_cache(tmp_path):
    cache = make_cache_store(tmp_path / "cache.json")
    seen = {}

    def ok_get(url, **kwargs):
        seen["url"] = url
        seen["timeout"] = kwargs["timeout"]
        return FakeResponse(200, catalog_text(REAL_STYLE_ENTRY, GITLAB_ENTRY).encode())

    svc = CatalogService(cache, http_get=ok_get)
    snapshot = svc.refresh()
    assert snapshot.source == "network" and len(snapshot.projects) == 2
    assert seen["url"] == "https://nolde.pages.dev/data/projects.json"
    assert seen["timeout"] == (10, 20)

    def down_get(url, **kwargs):
        raise requests.ConnectionError("offline")

    offline = CatalogService(cache, http_get=down_get)
    with pytest.raises(CatalogError):
        offline.refresh()
    cached = offline.load_cached()
    assert cached is not None and cached.source == "cache"
    assert [p.id for p in cached.projects] == ["banjo-recomp", "extreme-g-recompiled"]


def test_offline_with_no_cache_returns_none(tmp_path):
    svc = CatalogService(make_cache_store(tmp_path / "none.json"), http_get=lambda *a, **k: 1 / 0)
    assert svc.load_cached() is None


def test_http_error_does_not_overwrite_cache(tmp_path):
    cache = make_cache_store(tmp_path / "c.json")
    CatalogService(cache, http_get=lambda *a, **k: FakeResponse(200, catalog_text(MINIMAL_ENTRY).encode())).refresh()
    with pytest.raises(CatalogError):
        CatalogService(cache, http_get=lambda *a, **k: FakeResponse(503, b"")).refresh()
    assert [p.id for p in CatalogService(cache, http_get=None).load_cached().projects] == ["bare"]


def test_catalog_url_must_be_https(tmp_path):
    with pytest.raises(ValueError):
        CatalogService(make_cache_store(tmp_path / "x.json"), url="http://example.com/c.json")
