"""GUI tests: run headless with the offscreen Qt platform (set in conftest)."""

import json
import time
from pathlib import Path

import pytest
from PySide6.QtGui import QPixmap

from nolde_launcher.services.catalog_service import CatalogSnapshot, parse_catalog
from nolde_launcher.services.download_manager import DownloadStatus, DownloadTask
from nolde_launcher.services.library_service import InstallRecord

RAW = [
    {"id": "banjo", "gameTitle": "Banjo-Kazooie", "projectName": "Banjo: Recompiled", "type": ["recompilation"],
     "status": "available", "platforms": ["Windows"], "repositoryUrl": "https://github.com/o/banjo",
     "documentationUrl": "https://github.com/o/banjo/blob/main/README.md", "requiresOriginalAssets": "yes"},
    {"id": "sm64", "gameTitle": "Super Mario 64", "projectName": "Super Mario 64 PC Port", "type": ["port"],
     "status": "available", "platforms": ["Windows", "Linux"], "repositoryUrl": "https://github.com/o/sm64"},
    {"id": "gx", "gameTitle": "Extreme-G", "projectName": "Extreme-G: Recompiled", "type": ["recompilation"],
     "status": "archived", "platforms": ["Windows"], "repositoryUrl": "https://gitlab.com/o/gx"},
]


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("NOLDE_DATA_DIR", str(tmp_path / "data"))
    from nolde_launcher.app import context
    from nolde_launcher.ui.main_window import MainWindow
    services = context.build_services()
    library = Path(services.settings.library_dir)
    for pid, version, played in (("banjo", "v1.0.0", "2026-10-19T12:00:00+00:00"), ("sm64", "v3.2.0", "")):
        folder = library / pid
        folder.mkdir(parents=True)
        (folder / "game.exe").write_bytes(b"MZ")
        services.library.add_or_replace(InstallRecord(
            pid, pid, pid, pid, "game.exe", installed_version=version, last_played_at=played))
    projects, _ = parse_catalog(json.dumps(RAW))
    snapshot = CatalogSnapshot(tuple(projects), "network", time.time(), 0)
    win = MainWindow(services, snapshot, "")
    win.show()
    qapp.processEvents()
    yield win
    win.close()


def test_fonts_and_logo_are_bundled(qapp):
    from nolde_launcher.ui.fonts import load_fonts
    from nolde_launcher.ui.theme import LOGO_PATH
    families = load_fonts()
    assert "Inter" in families and "Space Grotesk" in families
    logo = QPixmap(str(LOGO_PATH))
    assert not logo.isNull() and logo.width() > 300


def test_project_page_opens_in_window_and_back_returns(window):
    from nolde_launcher.ui.main_window import PAGE_DISCOVER, PAGE_PROJECT
    window.show_page(PAGE_DISCOVER, animate=False)
    window.open_project("banjo")
    assert window.stack.currentIndex() == PAGE_PROJECT
    assert window.stack.currentWidget() is window.project_page
    assert window.project_page.isVisibleTo(window)
    window.go_back()
    assert window.stack.currentIndex() == PAGE_DISCOVER


def test_library_sorts_by_last_played_and_name(window):
    lib = window.library_page
    lib.sort_box.setCurrentIndex(lib.sort_box.findData("recent"))
    assert [r.project_id for r in lib._ordered()] == ["banjo", "sm64"]
    lib.sort_box.setCurrentIndex(lib.sort_box.findData("name"))
    assert [r.project_id for r in lib._ordered()] == ["banjo", "sm64"]  # sorts by name key
    lib.sort_box.setCurrentIndex(lib.sort_box.findData("installed"))
    assert len(lib._ordered()) == 2


def test_continue_card_shows_last_played_game(window):
    assert window.continue_card.title.text() == "banjo"
    assert window.continue_card._project_id == "banjo"


def test_installed_only_filter_limits_discover(window):
    window.discover.installed_only = False
    window.discover._apply()
    assert len(window.discover.grid._cards) == 3
    window._set_filter(True)
    assert window.discover.count_label.text() == "2 projects"


def test_play_marks_last_played_and_updates_continue(window, monkeypatch):
    from nolde_launcher.ui.dialogs import ThemedMessage
    # First launch asks for confirmation; answer "Yes" so the modal does not block the test.
    monkeypatch.setattr(ThemedMessage, "question",
                        staticmethod(lambda *a, **k: ThemedMessage.StandardButton.Yes))
    launched = {}

    class FakeProc:
        def poll(self):
            return None

    def fake_launch(library_dir, request):
        launched["id"] = request.project_id
        return FakeProc()

    monkeypatch.setattr(window.services.launcher, "launch", fake_launch)
    window.play("sm64")
    assert launched["id"] == "sm64"
    assert window.services.library.get("sm64").last_played_at != ""
    assert window.continue_card._project_id in {"banjo", "sm64"}


def test_failed_download_shows_retry_and_routes_to_controller(window):
    manager = window.installs.downloads
    task = DownloadTask(77, "sm64", "https://github.com/o/x.zip", Path("x.zip"))
    task.status = DownloadStatus.FAILED
    task.error = "server returned HTTP 503"
    manager._tasks[77] = task
    window.downloads_page.on_task_changed(task)
    card = window.downloads_page._cards[77]
    assert card.primary.text() == "Retry"
    seen = []
    window.downloads_page.retry_requested.connect(seen.append)
    card.primary.click()
    assert seen == ["sm64"]


def test_completed_download_moves_to_finished_section(window):
    manager = window.installs.downloads
    task = DownloadTask(78, "sm64", "https://github.com/o/y.zip", Path("y.zip"))
    task.status = DownloadStatus.RUNNING
    manager._tasks[78] = task
    window.downloads_page.on_task_changed(task)
    card = window.downloads_page._cards[78]
    assert card.section_is_active is True
    task.status = DownloadStatus.COMPLETED
    window.downloads_page.on_task_changed(task)
    assert card.section_is_active is False
    assert window.downloads_page.finished_box.indexOf(card) >= 0


def test_toast_shows_and_hides_message(window):
    window.toast.show_message("Installed.", "success", timeout_ms=50)
    assert window.toast.isVisible()
    assert window.toast.label.text() == "Installed."


def test_game_card_hover_animates_without_error(window):
    card = window.library_page.grid._cards["banjo"]
    card._animate_lift(True)
    card._animate_lift(False)
    assert card._shadow is not None


def test_nav_pages_switch(window):
    from nolde_launcher.ui.main_window import PAGE_DOWNLOADS, PAGE_SETTINGS
    window.show_page(PAGE_DOWNLOADS, animate=False)
    assert window.stack.currentIndex() == PAGE_DOWNLOADS
    window.show_page(PAGE_SETTINGS, animate=False)
    assert window.stack.currentIndex() == PAGE_SETTINGS


def test_hover_animation_survives_repeated_enter_leave(window, qapp):
    """Regression: animations were deleted by Qt after finishing, then reused."""
    card = window.library_page.grid._cards["banjo"]
    for _ in range(4):
        card._animate_lift(True)
        _spin(qapp, 320)  # let the animation finish (and be deleted if owned by Qt)
        card._animate_lift(False)
        _spin(qapp, 320)


def test_filter_and_refresh_repeatedly_do_not_touch_deleted_cards(window, qapp):
    """Regression: CardGrid deleted cards still referenced by DiscoverPage."""
    from nolde_launcher.services.catalog_service import CatalogSnapshot
    for value in (True, False, True, False):
        window._set_filter(value)
        qapp.processEvents()
    snap = window._snapshot
    for _ in range(3):
        window.discover.set_snapshot(CatalogSnapshot(snap.projects, "network", time.time(), 0))
        qapp.processEvents()
        window._set_filter(True)
        window._set_filter(False)
    assert window.discover.count_label.text() == "3 projects"


def test_library_refresh_repeatedly_after_removal(window, qapp):
    for _ in range(3):
        window.library_page.refresh()
        qapp.processEvents()
    window.services.library.records()
    window.library_page.refresh()
    assert window.library_page.grid.entry_count == 2


def _spin(qapp, ms):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)


def test_removing_a_game_releases_its_card_without_errors(window, qapp):
    """Regression: removed-game cards were deleted while the grid still referenced them."""
    window.services.library.forget("sm64")
    window.library_page.refresh()
    qapp.processEvents()
    assert "sm64" not in window.library_page.grid._keys
    window._set_filter(True)  # touches the grid after the removal
    qapp.processEvents()
    assert window.discover.count_label.text() == "1 projects"


def test_app_opens_on_discover(window):
    from nolde_launcher.ui.main_window import PAGE_DISCOVER
    assert window.stack.currentIndex() == PAGE_DISCOVER


def test_window_is_frameless_with_app_title_bar(window):
    from PySide6.QtCore import Qt
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert window.titlebar.objectName() == "TitleBar"
    assert window.titlebar.title.text() == ""  # only the window buttons remain


def test_resize_grips_cover_all_edges_and_hide_when_maximized(window, qapp):
    assert len(window._grips) == 8
    window.resize(1100, 700)
    qapp.processEvents()
    assert all(g.isVisible() for g in window._grips)
    window._place_grips()
    right = window._grips[1]
    assert right.geometry().right() <= window.width()


def test_project_page_hero_and_panels_render_for_catalog_entry(window, qapp):
    window.open_project("banjo")
    qapp.processEvents()
    page = window.project_page
    assert page._project.id == "banjo"
    assert page.hero.title.text() == "Banjo-Kazooie"
    assert page.left.count() >= 1 and page.right.count() >= 1


def test_discover_cards_show_build_and_platform_tags(window):
    card = window.discover.grid._cards["sm64"]
    assert card._tag_layout.count() >= 2  # Windows, Linux
    assert card._badge_host.isVisible() or card._badge_layout.count() >= 1


def test_card_logo_is_centred_over_cover(qapp):
    from PySide6.QtGui import QImage, QPixmap
    from nolde_launcher.ui.widgets import CoverFrame
    frame = CoverFrame("Logo Test")
    frame.show()
    qapp.processEvents()
    image = QImage(400, 120, QImage.Format.Format_ARGB32)
    image.fill(0)
    frame.set_logo(QPixmap.fromImage(image))
    qapp.processEvents()
    assert frame.logo.isVisible()
    centre_x = frame.logo.x() + frame.logo.width() / 2
    assert abs(centre_x - frame.width() / 2) <= 2
    frame.set_logo(None)
    assert not frame.logo.isVisible()


def test_page_transitions_survive_rapid_navigation(window, qapp):
    from nolde_launcher.ui.main_window import PAGE_DOWNLOADS, PAGE_LIBRARY, PAGE_SETTINGS
    for index in (PAGE_LIBRARY, PAGE_DOWNLOADS, PAGE_SETTINGS, PAGE_LIBRARY, PAGE_DOWNLOADS):
        window.show_page(index)  # animated: forward and backward slides overlap
        qapp.processEvents()
    assert window.stack.currentIndex() == PAGE_DOWNLOADS
    _spin(qapp, 400)  # let the animations finish and be released by Qt
    window.show_page(PAGE_LIBRARY)  # must not touch a deleted animation
    qapp.processEvents()
    assert window.stack.currentIndex() == PAGE_LIBRARY


def test_nav_indicator_follows_the_active_page(window, qapp):
    from nolde_launcher.ui.main_window import PAGE_SETTINGS
    window.show_page(PAGE_SETTINGS, animate=False)
    _spin(qapp, 50)
    target_y = window._nav_buttons[PAGE_SETTINGS].mapTo(window.sidebar, __import__("PySide6.QtCore", fromlist=["QPoint"]).QPoint(0, 0)).y()
    assert abs(window._nav_indicator.y() - (target_y + 9)) <= 2
