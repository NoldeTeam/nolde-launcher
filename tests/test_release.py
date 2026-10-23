import pytest
import requests

from nolde_launcher.models.project import CatalogProject
from nolde_launcher.services.release_service import (
    GitHubReleaseProvider, ReleaseError, parse_github_repo,
)
from nolde_launcher.services.source_resolver import PrimaryAction, SourceResolver
from tests.helpers import FakeResponse


def asset(name, size=100):
    return {"name": name, "browser_download_url": f"https://github.com/o/r/releases/download/v1/{name}",
            "size": size, "state": "uploaded"}


def release(tag, assets, prerelease=False, draft=False):
    return {"tag_name": tag, "name": tag, "prerelease": prerelease, "draft": draft,
            "published_at": "2026-01-01T00:00:00Z", "html_url": f"https://github.com/o/r/releases/tag/{tag}",
            "assets": assets}


def provider_with(payload=None, status=200, headers=None, raises=None):
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        if raises:
            raise raises
        return FakeResponse(status, headers=headers, json_data=payload)

    return GitHubReleaseProvider(http_get=get), calls


@pytest.mark.parametrize("url,expected", [
    ("https://github.com/Rainchus/Donkey-Kong-64-Recompiled", ("Rainchus", "Donkey-Kong-64-Recompiled")),
    ("https://github.com/owner/repo.git", ("owner", "repo")),
    ("https://gitlab.com/sonicdcer/ExtremeGRecomp", None),
    ("http://github.com/owner/repo", None),
    ("https://github.com/owner", None),
    ("https://github.com/owner/repo/extra/path", ("owner", "repo")),
    ("https://github.com/../etc", None),
    ("https://github.com/owner/..", None),
    ("https://evil.example.com/owner/repo", None),
    ("", None),
])
def test_repo_parsing_is_strict(url, expected):
    assert parse_github_repo(url) == expected


def test_repository_without_releases_is_reported():
    provider, _ = provider_with([])
    with pytest.raises(ReleaseError) as info:
        provider.resolve("https://github.com/o/empty")
    assert info.value.kind == "no_release"


def test_missing_repository_is_not_found():
    provider, _ = provider_with(status=404)
    with pytest.raises(ReleaseError) as info:
        provider.resolve("https://github.com/o/gone")
    assert info.value.kind == "not_found"


def test_rate_limit_is_distinguished():
    provider, _ = provider_with(status=403, headers={"X-RateLimit-Remaining": "0"})
    with pytest.raises(ReleaseError) as info:
        provider.resolve("https://github.com/o/r")
    assert info.value.kind == "rate_limited"


def test_network_failure_is_reported():
    provider, _ = provider_with(raises=requests.ConnectionError("down"))
    with pytest.raises(ReleaseError) as info:
        provider.resolve("https://github.com/o/r")
    assert info.value.kind == "network"


def test_source_archives_are_not_treated_as_builds():
    provider, _ = provider_with([release("v1", [
        asset("Source code (zip).zip"), asset("source-code.tar.gz"), asset("RepoSrc.zip"),
    ])])
    build = provider.resolve("https://github.com/o/r")
    assert build.asset is None
    names = [a.name for a in build.release.assets]
    assert "Source code (zip).zip" not in names
    assert "source-code.tar.gz" not in names
    assert "no Windows build is listed" in build.reason


def test_windows_zip_is_selected_and_prefers_x64():
    provider, _ = provider_with([release("v2", [
        asset("Game-linux.zip"), asset("Game-windows-x86.zip"), asset("Game-Windows-x64.zip"),
        asset("Game-win64.7z"),
    ])])
    build = provider.resolve("https://github.com/o/r")
    assert build.asset.name == "Game-Windows-x64.zip"
    assert build.release.tag == "v2"


def test_drafts_are_ignored_and_stable_preferred_over_prerelease():
    provider, _ = provider_with([
        release("v9-draft", [asset("Game-win.zip")], draft=True),
        release("v2-beta", [asset("Game-win.zip")], prerelease=True),
        release("v1", [asset("Game-win.zip")]),
    ])
    build = provider.resolve("https://github.com/o/r")
    assert build.release.tag == "v1" and build.release.prerelease is False


def test_prerelease_used_only_when_no_stable_build_exists():
    provider, _ = provider_with([
        release("v1", [asset("notes.txt")]),
        release("v2-rc", [asset("Game-win.zip")], prerelease=True),
    ])
    assert provider.resolve("https://github.com/o/r").release.tag == "v2-rc"


def test_release_metadata_is_cached_between_lookups():
    provider, calls = provider_with([release("v1", [asset("Game-win.zip")])])
    provider.resolve("https://github.com/o/r")
    provider.resolve("https://github.com/o/r")
    assert len(calls) == 1


def test_resolver_gitlab_project_falls_back_to_project_page():
    project = CatalogProject.from_dict({
        "id": "x", "gameTitle": "G", "projectName": "G Recomp",
        "repositoryUrl": "https://gitlab.com/a/b", "officialUrl": "https://example.org/",
    })
    result = SourceResolver([GitHubReleaseProvider(http_get=lambda *a, **k: 1 / 0)]).resolve(project)
    assert result.action is PrimaryAction.OPEN_PAGE
    assert result.reason_key == "availability.gitlab_note"
    assert result.page_url == "https://example.org/"


def test_resolver_without_any_source_is_unavailable():
    project = CatalogProject.from_dict({"id": "x", "gameTitle": "G", "projectName": "P"})
    result = SourceResolver([]).resolve(project)
    assert result.action is PrimaryAction.UNAVAILABLE


def test_resolver_returns_install_for_verified_windows_build():
    provider, _ = provider_with([release("v1", [asset("Game-Windows.zip")])])
    project = CatalogProject.from_dict({"id": "x", "gameTitle": "G", "projectName": "P",
                                        "repositoryUrl": "https://github.com/o/r"})
    result = SourceResolver([provider]).resolve(project)
    assert result.action is PrimaryAction.INSTALL
    assert result.build.asset.name == "Game-Windows.zip"


def test_asset_digest_is_parsed_as_trusted_sha256():
    digest = "a" * 64
    a = asset("Game-Windows.zip")
    a["digest"] = f"sha256:{digest}"
    provider, _ = provider_with([release("v1", [a])])
    build = provider.resolve("https://github.com/o/r")
    assert build.asset.sha256 == digest


def test_malformed_digest_is_ignored():
    a = asset("Game-Windows.zip")
    a["digest"] = "sha256:not-hex"
    provider, _ = provider_with([release("v1", [a])])
    assert provider.resolve("https://github.com/o/r").asset.sha256 == ""


# ---- OS classification: regression for Linux x64 builds being installed as Windows ----

from nolde_launcher.services.release_service import classify_os  # noqa: E402


def test_linux_x64_is_never_mistaken_for_windows():
    provider, _ = provider_with([release("v1", [asset("Game-Linux-x64.zip")])])
    build = provider.resolve("https://github.com/o/r")
    assert build.asset is None
    assert "only publishes non-Windows builds" in build.reason


def test_windows_build_is_chosen_over_linux_when_both_exist():
    provider, _ = provider_with([release("v1", [
        asset("Game-Linux-x64.zip"), asset("Game-Windows-x64.zip")])])
    assert provider.resolve("https://github.com/o/r").asset.name == "Game-Windows-x64.zip"


def test_unlabelled_zip_is_not_assumed_to_be_windows():
    provider, _ = provider_with([release("v1", [asset("Game-x64.zip")])])
    assert provider.resolve("https://github.com/o/r").asset is None


def test_windows_archive_in_7z_is_reported_not_downloaded():
    provider, _ = provider_with([release("v1", [
        asset("Game-Linux.zip"), asset("Game-Windows.7z")])])
    build = provider.resolve("https://github.com/o/r")
    assert build.asset is None
    assert "not a .zip archive" in build.reason


def test_older_release_with_windows_build_is_used_when_newest_is_linux_only():
    provider, _ = provider_with([
        release("v2", [asset("Game-Linux.zip")]),
        release("v1", [asset("Game-Windows.zip")]),
    ])
    build = provider.resolve("https://github.com/o/r")
    assert build.asset.name == "Game-Windows.zip" and build.release.tag == "v1"


def test_os_classification_table():
    assert classify_os("Game-Windows-x64.zip") == "windows"
    assert classify_os("game_win64.zip") == "windows"
    assert classify_os("Game-linux.zip") == "other"
    assert classify_os("Game-macOS.zip") == "other"
    assert classify_os("Game-Linux-Windows-compat.zip") == "other"
    assert classify_os("Game-x64.zip") == ""
    assert classify_os("twinkle-engine.zip") == ""  # 'twin' is not 'win'
