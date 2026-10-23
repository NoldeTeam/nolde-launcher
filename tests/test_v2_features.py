"""Tests for the v2 features: virtualised grid, motion levels, disk cache, play time,
game and launcher updates, pause and resume, diagnostics, sorting and shortcuts."""

import hashlib
import json
import sys
import time
from pathlib import Path

import pytest
import requests
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from nolde_launcher.models.project import CatalogProject
from nolde_launcher.services.download_manager import (DownloadPaused, DownloadStatus,
                                                      DownloadTask, download_to_file)
from nolde_launcher.services.release_service import ReleaseAsset, ReleaseInfo, ResolvedBuild
from nolde_launcher.services.source_resolver import Availability, PrimaryAction
from nolde_launcher.services.update_service import (LauncherUpdateError, check_game_updates,
                                                    download_launcher_package, is_newer,
                                                    parse_manifest)
from nolde_launcher.services.diagnostics import redact
from nolde_launcher.storage.settings import SettingsService
from tests.helpers import FakeResponse, FakeSession


# ----- settings: one motion level, migrated from the old switches -----

def test_old_animation_switches_migrate_to_motion_level(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"schema_version": 2, "animations": False}))
    assert SettingsService(p).settings.motion_level == "off"
    p.write_text(json.dumps({"schema_version": 2, "hover_effects": False}))
    assert SettingsService(p).settings.motion_level == "reduced"


def test_invalid_motion_level_is_rejected(tmp_path):
    svc = SettingsService(tmp_path / "s.json")
    svc.update(motion_level="turbo")
    assert svc.settings.motion_level in ("full", "reduced", "off")


def test_motion_levels_gate_each_kind_of_effect():
    from nolde_launcher.ui import motion
    motion.configure("reduced")
    assert motion.animations_enabled() and not motion.card_motion_enabled() and not motion.hover_enabled()
    motion.configure("off")
    assert not motion.animations_enabled()
    motion.configure("full")
    assert motion.card_motion_enabled() and motion.hover_enabled()


# ----- virtualised grid -----

def _fixed_card(key):
    holder = QWidget()
    layout = QVBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    inner = QLabel(str(key))
    inner.setFixedSize(264, 330)
    layout.addWidget(inner)
    return holder


def test_grid_builds_only_the_visible_cards(qapp):
    from nolde_launcher.ui.card_grid import CardGrid
    grid = CardGrid("", 240)
    grid.resize(800, 600)
    grid.show()
    grid.set_entries(list(range(500)), _fixed_card)
    qapp.processEvents()
    assert 0 < grid.built_count < 60, grid.built_count
    grid.verticalScrollBar().setValue(grid.verticalScrollBar().maximum())
    qapp.processEvents()
    assert 499 in grid._cards and 0 not in grid._cards  # far cards released, end cards built


def test_wrapped_cards_do_not_overlap_in_a_row(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("NOLDE_DATA_DIR", str(tmp_path / "d"))
    from nolde_launcher.ui.card_grid import CardGrid
    from nolde_launcher.ui.widgets import GameCard
    long_text = "A long description that wraps over several lines. " * 8

    def card(key):
        return GameCard(str(key), f"Game {key}", "by someone", description=long_text,
                        badges=(("Build possible", "success"),), tags=("Windows", "Linux"), width=240)

    grid = CardGrid("", 240)
    grid.resize(900, 700)
    grid.show()
    grid.set_entries(list(range(6)), card)
    for _ in range(5):
        qapp.processEvents()
    built = sorted(grid._cards.items(), key=lambda kv: kv[0])
    first_row = [c for k, c in built if k < grid._columns]
    second_row = [c for k, c in built if grid._columns <= k < 2 * grid._columns]
    for above, below in zip(first_row, second_row):
        assert below.y() >= above.y() + above.height(), "cards in the next row overlap"


# ----- disk cache -----

def test_disk_cache_removes_oldest_artwork_first(qapp, tmp_path):
    from nolde_launcher.ui.image_cache import ImageCache
    cache = ImageCache(tmp_path)
    folder = tmp_path / "covers"
    for i, name in enumerate(("old", "mid", "new")):
        f = folder / f"{name}.img"
        f.write_bytes(b"x" * 1024 * 1024)  # 1 MB each
        t = time.time() - (3 - i) * 100
        import os
        os.utime(f, (t, t))
    cache._disk_limit = 2 * 1024 * 1024
    freed = cache.prune_disk()
    assert freed == 1024 * 1024
    assert not (folder / "old.img").exists() and (folder / "new.img").exists()


def test_clear_disk_empties_the_artwork_folder(qapp, tmp_path):
    from nolde_launcher.ui.image_cache import ImageCache
    cache = ImageCache(tmp_path)
    (tmp_path / "covers" / "a.img").write_bytes(b"1")
    cache.clear_disk()
    assert cache.disk_usage() == 0


# ----- play time -----

@pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX shell script")
def test_playtime_is_measured_when_a_game_exits(tmp_path, monkeypatch):
    from nolde_launcher.services.launch_manager import LaunchManager, LaunchRequest
    monkeypatch.setenv("NOLDE_DATA_DIR", str(tmp_path / "d"))
    library = tmp_path / "library"
    (library / "Demo").mkdir(parents=True)
    exe = library / "Demo" / "demo.sh"
    exe.write_text("#!/bin/sh\nsleep 0.4\n")
    exe.chmod(0o755)
    manager = LaunchManager()
    proc = manager.launch(library, LaunchRequest("demo", "Demo", "demo.sh"))
    proc.wait(timeout=10)
    results = manager.pop_finished_playtime()
    assert results and results[0][0] == "demo" and results[0][1] >= 0.3
    assert manager.pop_finished_playtime() == []  # reported once


def test_playtime_accumulates_in_the_library(tmp_path):
    from nolde_launcher.services.library_service import InstallRecord, LibraryService, make_library_store
    library = tmp_path / "library"
    (library / "Demo").mkdir(parents=True)
    path = tmp_path / "l.json"
    svc = LibraryService(make_library_store(path), library)
    svc.add_or_replace(InstallRecord("demo", "D", "D", "Demo", "d.exe"))
    svc.add_playtime("demo", 90.7)
    svc.add_playtime("demo", 30)
    assert LibraryService(make_library_store(path), library).get("demo").play_seconds == 120


# ----- game updates -----

class _FakeResolver:
    def __init__(self, tags, action=PrimaryAction.INSTALL):
        self.tags = tags
        self.action = action

    def resolve(self, project):
        tag = self.tags.get(project.id)
        if tag is None:
            return Availability(PrimaryAction.OPEN_PAGE)
        asset = ReleaseAsset("g-Windows.zip", "https://github.com/o/x.zip", 1, True, True, True, "")
        build = ResolvedBuild("github", "o/x", ReleaseInfo(tag, tag, False, "", "", (asset,)), asset)
        return Availability(self.action, build=build)


def _project(pid):
    return CatalogProject(id=pid, game_title=pid, project_name=pid, repository_url="https://github.com/o/x")


def _record(pid, version):
    from nolde_launcher.services.library_service import InstallRecord
    return InstallRecord(pid, pid, pid, pid, "g.exe", installed_version=version)


def test_newer_release_is_reported_as_an_update():
    projects = {"a": _project("a"), "b": _project("b"), "c": _project("c")}
    resolver = _FakeResolver({"a": "v2.0", "b": "v1.0", "c": "v3.0"})
    found = check_game_updates([_record("a", "v1.0"), _record("b", "v1.0"), _record("c", "v2.0")],
                               projects.get, resolver)
    assert found == {"a": "v2.0", "c": "v3.0"}  # same version is not an update


def test_projects_without_a_verified_build_are_skipped():
    projects = {"a": _project("a")}
    resolver = _FakeResolver({"a": "v2.0"}, action=PrimaryAction.OPEN_PAGE)
    assert check_game_updates([_record("a", "v1.0")], projects.get, resolver) == {}


def test_update_keeps_existing_executable_when_it_still_exists():
    from nolde_launcher.ui.install_controller import InstallController
    pick = InstallController._pick_executable.__get__(object())
    previous = _record("a", "v1.0")
    previous.main_executable = "bin/game.exe"
    assert pick(["bin/game.exe", "other.exe"], previous) == ("bin/game.exe", "installed")
    previous.main_executable = "gone.exe"
    assert pick(["only.exe"], previous) == ("only.exe", "installed")
    assert pick([], previous) == ("", "needs_setup")


# ----- pause and resume -----

def test_pause_keeps_partial_data_and_resume_continues_it(tmp_path):
    url = "https://github.com/o/r/releases/download/v1/Game-Windows.zip"
    body = b"z" * 4000
    dest = tmp_path / "g.zip"
    pause = __import__("threading").Event()
    calls = {"n": 0}

    class Pausing(FakeResponse):
        def iter_content(self, chunk_size=1024):
            for i in range(0, len(self._body), 1000):
                yield self._body[i:i + 1000]
                calls["n"] += 1
                if calls["n"] == 2:
                    pause.set()

    sess = FakeSession(lambda u, k: Pausing(200, body, {"Content-Length": str(len(body))}, url=url))
    with pytest.raises(DownloadPaused):
        download_to_file(url, dest, session=sess, pause_event=pause)
    part = tmp_path / "g.zip.part"
    assert part.exists() and 0 < part.stat().st_size < len(body)

    seen = {}

    def resume(u, kwargs):
        seen.update(kwargs["headers"])
        done = part.stat().st_size
        return FakeResponse(206, body[done:], {"Content-Length": str(len(body) - done)}, url=url)

    out = download_to_file(url, dest, session=FakeSession(resume))
    assert seen["Range"].startswith("bytes=") and out.read_bytes() == body


def test_manager_pause_then_resume_then_complete(qapp, tmp_path):
    import threading
    from nolde_launcher.services.download_manager import DownloadManager
    url = "https://github.com/o/r/releases/download/v1/Game-Windows.zip"
    body = b"q" * 3000
    gate = threading.Event()

    class Slow(FakeResponse):
        def iter_content(self, chunk_size=1024):
            yield body[:1000]
            gate.wait(3)
            yield body[1000:]

    manager = DownloadManager(session_factory=lambda: FakeSession(
        lambda u, k: Slow(200, body, {"Content-Length": str(len(body))}, url=url)))
    task = manager.enqueue("proj", url, tmp_path / "x.zip")
    _wait(lambda: task.bytes_done > 0)
    manager.pause(task.task_id)
    _wait(lambda: task.status is DownloadStatus.PAUSED)
    assert task.is_active  # paused counts as active, so it stays in the Active list
    gate.set()
    assert manager.resume(task.task_id)
    _wait(lambda: task.status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED))
    assert task.status is DownloadStatus.COMPLETED


def test_cancelling_a_paused_download_removes_its_partial_file(qapp, tmp_path):
    from nolde_launcher.services.download_manager import DownloadManager
    manager = DownloadManager(session_factory=lambda: FakeSession(
        lambda u, k: FakeResponse(200, b"abc", {}, url=u)))
    dest = tmp_path / "p.zip"
    task = DownloadTask(99, "x", "https://github.com/a.zip", dest, status=DownloadStatus.PAUSED)
    (tmp_path / "p.zip.part").write_bytes(b"partial")
    manager._tasks[99] = task
    manager.cancel(99)
    assert task.status is DownloadStatus.CANCELLED
    assert not (tmp_path / "p.zip.part").exists()


def _wait(predicate, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met in time")


# ----- launcher update manifest -----

GOOD = {"version": "0.2.0", "url": "https://github.com/nolde/launcher/releases/download/v0.2.0/NoldeLauncher-0.2.0.zip",
        "sha256": "a" * 64, "notes": "Fixes"}


def test_valid_manifest_is_accepted_and_compared_numerically():
    manifest = parse_manifest(json.dumps(GOOD))
    assert manifest.version == "0.2.0"
    assert is_newer("0.10.0", "0.9.0") and not is_newer("0.1.0", "0.1.0")


@pytest.mark.parametrize("change", [
    {"url": "http://github.com/x.zip"},                # not HTTPS
    {"url": "https://evil.example.com/x.zip"},         # not an allowed host
    {"sha256": "not-a-hash"},                          # no valid SHA-256
    {"version": "latest"},                             # not numeric
])
def test_invalid_manifests_are_rejected(change):
    with pytest.raises(LauncherUpdateError):
        parse_manifest(json.dumps({**GOOD, **change}))


def test_launcher_package_with_wrong_hash_is_deleted(tmp_path):
    from nolde_launcher.services.update_service import LauncherManifest
    body = b"package bytes"
    url = "https://github.com/nolde/launcher/releases/download/v0.2.0/Pkg.zip"
    manifest = LauncherManifest("0.2.0", url, "0" * 64)
    sess = FakeSession(lambda u, k: FakeResponse(200, body, {"Content-Length": str(len(body))}, url=url))
    with pytest.raises(LauncherUpdateError):
        download_launcher_package(manifest, tmp_path, session=sess)
    assert not (tmp_path / "Pkg.zip").exists()


def test_launcher_package_with_correct_hash_is_saved(tmp_path):
    from nolde_launcher.services.update_service import LauncherManifest
    body = b"package bytes"
    url = "https://github.com/nolde/launcher/releases/download/v0.2.0/Pkg.zip"
    manifest = LauncherManifest("0.2.0", url, hashlib.sha256(body).hexdigest())
    sess = FakeSession(lambda u, k: FakeResponse(200, body, {"Content-Length": str(len(body))}, url=url))
    saved = download_launcher_package(manifest, tmp_path, session=sess)
    assert saved.read_bytes() == body


def test_no_update_source_is_reported_plainly():
    from nolde_launcher.services.update_service import fetch_manifest
    with pytest.raises(LauncherUpdateError, match="no update source"):
        fetch_manifest("", requests.get)


# ----- diagnostics privacy -----

def test_diagnostics_redacts_home_folder_and_user_name(monkeypatch):
    monkeypatch.setattr("getpass.getuser", lambda: "yanpc")
    home = str(Path.home())
    text = redact(f"opened {home}/Downloads/x.zip by yanpc")
    assert home not in text and "yanpc" not in text
    assert "~" in text and "<user>" in text


# ----- sorting -----

def test_discover_sorting_options():
    from nolde_launcher.ui.discover_page import sort_projects
    projects = [
        CatalogProject(id="a", game_title="Zed", project_name="Z", last_updated="2026-01-05", progress=40),
        CatalogProject(id="b", game_title="Alpha", project_name="A", last_updated="2026-07-01", progress=90),
        CatalogProject(id="c", game_title="Mid", project_name="M", last_updated="", progress=None),
    ]
    assert [p.id for p in sort_projects(projects, "name")] == ["b", "c", "a"]
    assert [p.id for p in sort_projects(projects, "updated")] == ["b", "a", "c"]
    assert [p.id for p in sort_projects(projects, "progress")] == ["b", "a", "c"]


# ----- keyboard shortcuts -----

@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("NOLDE_DATA_DIR", str(tmp_path / "data"))
    from nolde_launcher.app import context
    from nolde_launcher.services.catalog_service import CatalogSnapshot, parse_catalog
    from nolde_launcher.ui.main_window import MainWindow
    services = context.build_services()
    raw = [{"id": "p0", "gameTitle": "Game", "projectName": "P", "type": ["port"], "status": "available",
            "platforms": ["Windows"], "repositoryUrl": "https://github.com/o/p0"}]
    projects, _ = parse_catalog(json.dumps(raw))
    win = MainWindow(services, CatalogSnapshot(tuple(projects), "network", time.time(), 0), "")
    win.show()
    qapp.processEvents()
    yield win
    win.close()


def test_ctrl_f_focuses_catalog_search(window, qapp):
    from nolde_launcher.ui.main_window import PAGE_DISCOVER
    window.show_page(0, animate=False)
    window._focus_search()
    qapp.processEvents()
    assert window.stack.currentIndex() == PAGE_DISCOVER
    assert window.discover.search.hasFocus()


def test_escape_leaves_the_project_page(window, qapp):
    from nolde_launcher.ui.main_window import PAGE_DISCOVER, PAGE_PROJECT
    window.show_page(PAGE_DISCOVER, animate=False)
    window.open_project("p0")
    assert window.stack.currentIndex() == PAGE_PROJECT
    window._escape()
    assert window.stack.currentIndex() == PAGE_DISCOVER


def test_site_button_and_diagnostics_action_exist(window):
    assert hasattr(window, "export_diagnostics") and hasattr(window, "check_launcher_update")


# ----- regressions: flicker and lag while scrolling the catalog -----

def test_hover_lift_is_suspended_while_the_grid_scrolls(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("NOLDE_DATA_DIR", str(tmp_path / "d"))
    from nolde_launcher.ui import motion
    from nolde_launcher.ui.widgets import GameCard
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication
    motion.configure("full")
    card = GameCard("x", "T", "")
    card.show()
    motion.set_scrolling(True)
    QApplication.sendEvent(card, QEvent(QEvent.Type.Enter))
    assert card._shadow is None, "a card passing under the pointer must not lift while scrolling"
    motion.set_scrolling(False)
    QApplication.sendEvent(card, QEvent(QEvent.Type.Enter))
    assert card._shadow is not None and card._shadow.isEnabled()


def test_shadow_is_switched_off_once_the_card_settles(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("NOLDE_DATA_DIR", str(tmp_path / "d"))
    from nolde_launcher.ui import motion
    from nolde_launcher.ui.widgets import GameCard
    motion.configure("full")
    motion.set_scrolling(False)
    card = GameCard("x", "T", "")
    card.show()

    def pump_until(condition, timeout=3.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            qapp.processEvents()  # animations only advance while the event loop runs
            if condition():
                return True
            time.sleep(0.005)
        return False

    card._animate_lift(True)
    assert pump_until(lambda: card._blur_anim.state() == card._blur_anim.State.Stopped)
    assert card._shadow.isEnabled()
    card._animate_lift(False)
    assert pump_until(lambda: not card._shadow.isEnabled())


def test_scrolling_reuses_cards_instead_of_creating_new_ones(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("NOLDE_DATA_DIR", str(tmp_path / "d"))
    from nolde_launcher.ui.card_grid import CardGrid
    created = {"n": 0}

    def card(key):
        created["n"] += 1
        return _fixed_card(key)

    def bind(widget, key):
        pass

    grid = CardGrid("", 240)
    grid.resize(800, 600)
    grid.show()
    grid.set_entries(list(range(400)), card, binder=bind)
    qapp.processEvents()
    sb = grid.verticalScrollBar()
    for value in range(0, sb.maximum(), 300):
        sb.setValue(value)
        qapp.processEvents()
    assert created["n"] < 40, f"{created['n']} cards were created while scrolling; they should be reused"
    assert grid.pool_count >= 0
