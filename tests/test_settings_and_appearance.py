"""Settings validation, live application of appearance options, and regressions for the
logo-position and banner-overlap bugs."""

import json
import time

import pytest
from PySide6.QtGui import QImage, QPixmap

from nolde_launcher.services.catalog_service import CatalogSnapshot, parse_catalog
from nolde_launcher.storage.settings import SettingsService


# ----- settings validation -----

def test_invalid_setting_values_fall_back_to_defaults(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"schema_version": 2, "grid_art": "hologram", "card_size": 9,
                                "animations": "yes", "image_cache_size": 7,
                                "max_concurrent_downloads": 99}))
    s = SettingsService(path).settings
    assert s.grid_art == "cover_logo"
    assert s.card_size == "medium"
    assert s.motion_level in ("full", "reduced")
    assert s.image_cache_size == 60
    assert s.max_concurrent_downloads == 2


def test_update_persists_and_validates(tmp_path):
    path = tmp_path / "s.json"
    svc = SettingsService(path)
    svc.update(grid_art="logo", card_size="large", load_images=False)
    again = SettingsService(path).settings
    assert again.grid_art == "logo" and again.card_size == "large" and again.load_images is False
    svc.update(grid_art="not-a-mode")  # invalid value keeps the previous setting
    assert svc.settings.grid_art == "logo"


def test_unknown_setting_is_rejected(tmp_path):
    with pytest.raises(KeyError):
        SettingsService(tmp_path / "s.json").update(theme="neon")


# ----- regression: logo jumped to the top-left corner on reload -----

def test_logo_is_centred_even_when_set_before_first_show(qapp):
    from nolde_launcher.ui.widgets import CoverFrame
    frame = CoverFrame("Reload")  # not shown yet, like a freshly rebuilt card
    image = QImage(300, 120, QImage.Format.Format_ARGB32)
    image.fill(0)
    frame.set_logo(QPixmap.fromImage(image))
    assert frame.logo.x() > 0 and frame.logo.y() > 0, "logo must not sit in the corner"
    centre_x = frame.logo.x() + frame.logo.width() / 2
    assert abs(centre_x - frame.width() / 2) <= 2


# ----- regression: text drawn over the logo on the project banner -----

def test_project_banner_grows_to_fit_its_text(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("NOLDE_DATA_DIR", str(tmp_path / "d"))
    from nolde_launcher.ui.project_page import HeroFrame, HERO_HEIGHT
    hero = HeroFrame()
    hero.resize(900, HERO_HEIGHT)
    hero.set_badges([(f"Badge {i}", "accent") for i in range(6)])  # many badges wrap the text block
    hero.set_title("A very long game title that takes more than one line", "Project name")
    image = QImage(460, 150, QImage.Format.Format_ARGB32)
    image.fill(0)
    hero.set_art(None, QPixmap.fromImage(image))
    qapp.processEvents()
    assert hero.minimumHeight() >= hero.overlay.sizeHint().height()
    assert hero.minimumHeight() >= HERO_HEIGHT


# ----- live application of settings in the running window -----

RAW = [{"id": f"p{i}", "gameTitle": f"Game {i}", "projectName": f"Project {i}", "type": ["port"],
        "status": "available", "platforms": ["Windows"], "repositoryUrl": f"https://github.com/o/p{i}"}
       for i in range(3)]


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("NOLDE_DATA_DIR", str(tmp_path / "data"))
    from nolde_launcher.app import context
    from nolde_launcher.ui.main_window import MainWindow
    services = context.build_services()
    projects, _ = parse_catalog(json.dumps(RAW))
    win = MainWindow(services, CatalogSnapshot(tuple(projects), "network", time.time(), 0), "")
    win.show()
    qapp.processEvents()
    yield win
    win.close()


def test_card_size_setting_changes_card_width_live(window, qapp):
    before = window.discover.grid._cards["p0"].width()
    window.services.settings.update(card_size="large")
    window.apply_settings()
    qapp.processEvents()
    after = window.discover.grid._cards["p0"].width()
    assert after > before


def test_text_only_mode_draws_no_logo(window, qapp):
    window.services.settings.update(grid_art="text")
    window.apply_settings()
    card = window.discover.grid._cards["p1"]
    assert not card.frame._has_logo


def test_load_images_off_disables_artwork_entirely(window):
    window.services.settings.update(load_images=False)
    window.apply_settings()
    assert window.images.pixmap("https://images.launchbox-app.com/x.png") is None


def test_animations_off_skips_fades_and_slides(window, qapp):
    from nolde_launcher.ui import motion
    from nolde_launcher.ui.widgets import fade_in
    window.services.settings.update(motion_level="off")
    window.apply_settings()
    assert motion.animations_enabled() is False
    probe = window.discover
    fade_in(probe)
    assert probe.graphicsEffect() is None


def test_image_cache_evicts_least_recently_used(qapp, tmp_path):
    from nolde_launcher.ui.image_cache import ImageCache
    cache = ImageCache(tmp_path)
    cache.set_limit(2)
    for name in ("a", "b", "c"):
        cache._remember(name, QPixmap(4, 4))
    assert cache.memory_count == 2
    assert "a" not in cache._pixmaps and "c" in cache._pixmaps


# ----- site button in the sidebar -----

def test_site_button_is_icon_only_and_opens_the_site(window):
    from PySide6.QtWidgets import QToolButton
    buttons = [b for b in window.sidebar.findChildren(QToolButton) if b.objectName() == "SiteButton"]
    assert len(buttons) == 1
    assert buttons[0].text() == ""
    assert buttons[0].toolTip() == "Nolde website"


# ----- regression: badges and tags were squeezed and cut short on narrow cards -----

def test_card_badges_and_tags_wrap_instead_of_being_cut(qapp):
    from nolde_launcher.ui.widgets import GameCard
    card = GameCard("x", "Sonic the Hedgehog", "by mstan", description="A static recompilation.",
                    badges=(("Build possible", "success"), ("Recompilation", "accent"),
                            ("Made with AI", "warning")),
                    tags=("Sega Mega Drive", "Sega Genesis", "Windows"))
    card.show()
    qapp.processEvents()
    for host in (card._badge_host, card._tag_host):
        for label in host.findChildren(type(card.title)):
            assert label.width() >= label.sizeHint().width(), label.text()
