"""User-added apps: validation, storage, release filtering, manual apps, files and mods."""

import io
import json
import zipfile

import pytest

from nolde_launcher.models.project import CatalogProject
from nolde_launcher.services.custom_apps import CustomAppError, CustomAppSpec, CustomAppStore, validate
from nolde_launcher.services.custom_install import finish_custom_install
from nolde_launcher.services.release_service import (ReleaseAsset, ReleaseInfo, ResolvedBuild,
                                                    asset_matches, choose_by_pattern)
from nolde_launcher.services.source_resolver import PrimaryAction, SourceResolver


def spec(**kw):
    base = dict(name="My Game", management="manual")
    base.update(kw)
    return CustomAppSpec(**base)


def managed(**kw):
    return spec(management="managed", repository_url="https://github.com/owner/game", **kw)


# ----- validation -----

def test_a_minimal_manual_app_is_valid():
    ok = validate(spec())
    assert ok.name == "My Game" and ok.repository_url == ""


def test_name_is_required():
    with pytest.raises(CustomAppError, match="Enter a name"):
        validate(spec(name="   "))


def test_manual_app_cannot_have_a_repository():
    with pytest.raises(CustomAppError, match="no repository"):
        validate(spec(repository_url="https://github.com/owner/game"))


def test_managed_app_needs_a_github_repository():
    with pytest.raises(CustomAppError, match="GitHub repository"):
        validate(spec(management="managed", repository_url="https://gitlab.com/a/b"))


@pytest.mark.parametrize("bad", ["../escape", "a/b", "CON.", ""])
def test_folder_name_must_be_a_safe_single_folder(bad):
    if bad == "":
        return  # empty means "use the name", covered below
    with pytest.raises(CustomAppError):
        validate(spec(folder_name=bad))


def test_empty_release_filter_uses_the_default_zip_pattern():
    assert validate(managed(asset_filter="")).asset_filter == "*.zip"


def test_empty_folder_name_uses_the_app_name():
    assert validate(spec(name="Super Game", folder_name="")).folder_name == "Super Game"


@pytest.mark.parametrize("pattern", ["a/b*.zip", "..\\x.zip"])
def test_release_filter_cannot_contain_path_parts(pattern):
    with pytest.raises(CustomAppError):
        validate(managed(asset_filter=pattern))


def test_icon_must_be_https():
    with pytest.raises(CustomAppError, match="https"):
        validate(spec(icon_url="http://example.com/i.png"))


def test_files_to_add_must_exist(tmp_path):
    with pytest.raises(CustomAppError, match="File not found"):
        validate(spec(files_to_add=[str(tmp_path / "missing.dll")]))


def test_mod_sources_must_be_github_repositories():
    with pytest.raises(CustomAppError, match="GitHub repository"):
        validate(spec(mods_path="mods", mod_sources=["https://example.com/mod"]))


@pytest.mark.parametrize("path", ["../mods", "/etc", "C:/mods"])
def test_mods_folder_must_stay_inside_the_game(path):
    with pytest.raises(CustomAppError, match="relative folder"):
        validate(spec(mods_path=path))


def test_mod_sources_need_a_mods_folder():
    with pytest.raises(CustomAppError, match="mods folder"):
        validate(spec(mod_sources=["https://github.com/a/b"]))


# ----- storage -----

def test_store_adds_updates_and_removes_apps(tmp_path):
    store = CustomAppStore(tmp_path / "apps.json")
    added = store.add(spec(name="One"))
    assert added.id.startswith("custom-") and len(added.id) > 10
    store.update(added.id, spec(name="One renamed"))
    assert CustomAppStore(tmp_path / "apps.json").get(added.id).name == "One renamed"
    store.remove(added.id)
    assert store.list() == []


def test_store_skips_damaged_entries(tmp_path):
    path = tmp_path / "apps.json"
    path.write_text(json.dumps({"schema_version": 1, "apps": [{"no": "id"}, "junk",
                                                             {"id": "custom-1", "name": "Ok"}]}))
    assert [a.id for a in CustomAppStore(path).list()] == ["custom-1"]


def test_to_project_maps_the_user_fields():
    project = managed(id="custom-x", display_name="Shown", author="Me", tags=["mod"],
                      mods_path="mods", mod_sources=["https://github.com/a/b"],
                      asset_filter="*Windows*.zip").to_project()
    assert project.custom and project.management == "managed"
    assert project.game_title == "Shown" and project.project_name == "My Game"
    assert project.authors == ("Me",) and project.tags == ("mod",)
    assert project.asset_filter == "*Windows*.zip" and project.mods_path == "mods"


# ----- release filter -----

def asset(name):
    return ReleaseAsset(name=name, download_url=f"https://github.com/o/r/{name}", size=1,
                        is_zip=name.lower().endswith(".zip"), is_windows_hint=False)


def test_glob_is_case_insensitive_and_zip_only():
    assert asset_matches("*windows*.zip", "Game-WINDOWS-x64.zip")
    assert not asset_matches("*windows*.zip", "Game-Windows.7z")
    assert not asset_matches("*", "readme.txt")


def test_user_filter_picks_the_matching_zip_even_when_it_is_not_windows_named():
    release = ReleaseInfo("v1", "v1", False, "", "", (asset("Linux.zip"), asset("Build-Final.zip")))
    assert choose_by_pattern(release, "Build-*.zip").name == "Build-Final.zip"
    assert choose_by_pattern(release, "*.tar") is None


# ----- resolver -----

class Recorder:
    def __init__(self):
        self.calls = []

    def supports(self, url):
        return True

    def resolve(self, url, pattern=""):
        self.calls.append((url, pattern))
        release = ReleaseInfo("v1", "v1", False, "", "", (asset("Build.zip"),))
        chosen = choose_by_pattern(release, pattern) if pattern else None
        return ResolvedBuild("github", "o/g", release, chosen)


def test_manual_apps_never_download():
    project = spec().to_project()
    result = SourceResolver([Recorder()]).resolve(project)
    assert result.action is PrimaryAction.MANUAL
    assert result.reason_key == "custom.manual_hint"


def test_managed_apps_pass_their_filter_to_the_provider():
    recorder = Recorder()
    project = managed(asset_filter="Build*.zip").to_project()
    result = SourceResolver([recorder]).resolve(project)
    assert recorder.calls == [("https://github.com/owner/game", "Build*.zip")]
    assert result.action is PrimaryAction.INSTALL and result.build.asset.name == "Build.zip"


# ----- files and mods after install -----

def make_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


class ModProvider:
    def __init__(self, archives):
        self.archives = archives  # repo url -> zip bytes, or None for "no build"

    def resolve(self, url, pattern=""):
        data = self.archives.get(url)
        if data is None:
            return ResolvedBuild("github", url, ReleaseInfo("v1", "v1", False, "", "", ()), None, "no build")
        a = ReleaseAsset(name="mod.zip", download_url=url + "/mod.zip", size=len(data),
                         is_zip=True, is_windows_hint=True)
        return ResolvedBuild("github", url, ReleaseInfo("v1", "v1", False, "", "", (a,)), a)


def test_files_are_copied_and_each_mod_gets_its_own_folder(tmp_path, monkeypatch):
    install = tmp_path / "Game"
    install.mkdir()
    dll = tmp_path / "extra.dll"
    dll.write_bytes(b"dll")
    mod = make_zip({"mod.txt": b"hello"})

    def fake_download(url, dest, session=None, expected_sha256=None, **kwargs):
        dest.write_bytes(mod)
        return dest

    monkeypatch.setattr("nolde_launcher.services.custom_install.download_to_file", fake_download)
    project = CatalogProject(id="c", game_title="G", project_name="G", custom=True, management="managed",
                             files_to_add=(str(dll),), mods_path="mods",
                             mod_sources=("https://github.com/owner/hd-mod",), mods_own_folder=True)
    problems = finish_custom_install(install, project, ModProvider({"https://github.com/owner/hd-mod": mod}),
                                     tmp_path / "work")
    assert problems == []
    assert (install / "extra.dll").read_bytes() == b"dll"
    assert (install / "mods" / "hd-mod" / "mod.txt").read_text() == "hello"


def test_a_failed_mod_is_reported_and_the_rest_still_install(tmp_path, monkeypatch):
    install = tmp_path / "Game"
    install.mkdir()
    mod = make_zip({"m.txt": b"ok"})

    def fake_download(url, dest, session=None, expected_sha256=None, **kwargs):
        dest.write_bytes(mod)
        return dest

    monkeypatch.setattr("nolde_launcher.services.custom_install.download_to_file", fake_download)
    project = CatalogProject(id="c", game_title="G", project_name="G", custom=True, management="managed",
                             mods_path="mods", mod_sources=("https://github.com/o/broken",
                                                           "https://github.com/o/good"),
                             mods_own_folder=False)
    provider = ModProvider({"https://github.com/o/good": mod})
    problems = finish_custom_install(install, project, provider, tmp_path / "work")
    assert len(problems) == 1 and problems[0].startswith("broken:")
    assert (install / "mods" / "m.txt").read_text() == "ok"  # shared folder: extracted directly


# ----- icons from user addresses -----

def test_only_the_address_the_user_entered_is_allowed_for_artwork(tmp_path):
    from nolde_launcher.ui.image_cache import ImageCache
    cache = ImageCache(tmp_path)
    assert not cache._url_allowed("https://example.org/icon.png")
    cache.allow_url("https://example.org/icon.png")
    assert cache._url_allowed("https://example.org/icon.png")
    assert not cache._url_allowed("https://example.org/other.png")
    cache.allow_url("http://insecure.example/x.png")  # refused: not https
    assert not cache._url_allowed("http://insecure.example/x.png")
