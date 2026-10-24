"""Launcher updates from GitHub releases, the early access label, the repository link and the
first-launch welcome."""

import hashlib
import json
import re

import pytest
from PySide6.QtWidgets import QToolButton

from nolde_launcher.app.version import REPO_URL, VERSION_LABEL, __version__
from nolde_launcher.services.update_service import (LauncherRelease, LauncherUpdateError,
                                                    check_latest_release, download_installer,
                                                    installer_arguments, is_newer, select_installer)
from tests.helpers import FakeResponse, FakeSession

SHA = "a" * 64
URL = "https://github.com/NoldeTeam/nolde-launcher/releases/download/v0.3.0/NoldeLauncher-Setup-0.3.0.exe"


def release(**overrides):
    data = {
        "tag_name": "v0.3.0", "draft": False, "prerelease": False, "html_url": "https://github.com/x",
        "body": "notes",
        "assets": [{"name": "NoldeLauncher-Setup-0.3.0.exe", "browser_download_url": URL,
                    "digest": f"sha256:{SHA}"}],
    }
    data.update(overrides)
    return data


def no_http(*a, **k):
    raise AssertionError("no network call expected")


# ----- version and early access -----

def test_version_label_follows_the_version_number():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)
    assert VERSION_LABEL == f"Early Access {__version__}"


@pytest.mark.parametrize("candidate,expected", [("0.3.1", True), ("0.10.0", True), ("0.3.0", False),
                                                ("0.2.9", False)])
def test_newer_versions_are_compared_numerically(candidate, expected):
    assert is_newer(candidate, "0.3.0") is expected


# ----- choosing the installer -----

def test_the_windows_installer_and_its_digest_are_selected():
    chosen = select_installer(release(), no_http)
    assert chosen == LauncherRelease("0.3.0", URL, SHA, "https://github.com/x", "notes")


def test_draft_and_prerelease_are_never_offered():
    with pytest.raises(LauncherUpdateError):
        select_installer(release(draft=True), no_http)
    with pytest.raises(LauncherUpdateError):
        select_installer(release(prerelease=True), no_http)


def test_release_without_matching_installer_is_refused():
    with pytest.raises(LauncherUpdateError, match="no Windows installer"):
        select_installer(release(assets=[{"name": "NoldeLauncher-Setup-0.2.0.exe",
                                          "browser_download_url": URL, "digest": f"sha256:{SHA}"}]), no_http)


def test_installer_from_an_unknown_host_is_refused():
    evil = release(assets=[{"name": "NoldeLauncher-Setup-0.3.0.exe",
                            "browser_download_url": "https://evil.example.com/setup.exe",
                            "digest": f"sha256:{SHA}"}])
    with pytest.raises(LauncherUpdateError, match="allowed HTTPS host"):
        select_installer(evil, no_http)


def test_missing_hash_falls_back_to_the_companion_sha256_file():
    data = release(assets=[
        {"name": "NoldeLauncher-Setup-0.3.0.exe", "browser_download_url": URL},
        {"name": "NoldeLauncher-Setup-0.3.0.exe.sha256",
         "browser_download_url": URL + ".sha256"},
    ])

    def http_get(url, **kwargs):
        return FakeResponse(200, f"{SHA}  NoldeLauncher-Setup-0.3.0.exe\n".encode(), url=url)

    assert select_installer(data, http_get).sha256 == SHA


def test_release_without_any_published_hash_is_refused():
    data = release(assets=[{"name": "NoldeLauncher-Setup-0.3.0.exe", "browser_download_url": URL}])
    with pytest.raises(LauncherUpdateError, match="does not publish a SHA-256"):
        select_installer(data, lambda url, **k: FakeResponse(404, b"", url=url))


# ----- checking GitHub -----

def github(status=200, payload=None):
    body = json.dumps(payload).encode() if payload is not None else b""
    return lambda url, **kwargs: FakeResponse(status, body, url=url)


def test_no_release_yet_means_nothing_to_offer():
    assert check_latest_release(github(404), current="0.3.0") is None


def test_same_version_is_not_offered():
    assert check_latest_release(github(200, release()), current="0.3.0") is None


def test_newer_release_is_offered():
    newer = release(tag_name="v0.3.1", assets=[{"name": "NoldeLauncher-Setup-0.3.1.exe",
                                                "browser_download_url": URL.replace("0.3.0", "0.3.1"),
                                                "digest": f"sha256:{SHA}"}])
    found = check_latest_release(github(200, newer), current="0.3.0")
    assert found is not None and found.version == "0.3.1"


def test_rate_limit_is_reported_clearly():
    with pytest.raises(LauncherUpdateError, match="limiting"):
        check_latest_release(github(403), current="0.3.0")


# ----- download and install -----

def test_downloaded_installer_with_a_wrong_hash_is_deleted(tmp_path):
    body = b"not the real installer"
    chosen = LauncherRelease("0.3.1", URL, "0" * 64, "https://github.com/x")
    session = FakeSession(lambda u, k: FakeResponse(200, body, {"Content-Length": str(len(body))}, url=URL))
    with pytest.raises(LauncherUpdateError):
        download_installer(chosen, tmp_path, session=session)
    assert not any(tmp_path.iterdir())


def test_downloaded_installer_with_the_right_hash_is_kept(tmp_path):
    body = b"installer bytes"
    chosen = LauncherRelease("0.3.1", URL, hashlib.sha256(body).hexdigest(), "https://github.com/x")
    session = FakeSession(lambda u, k: FakeResponse(200, body, {"Content-Length": str(len(body))}, url=URL))
    saved = download_installer(chosen, tmp_path, session=session)
    assert saved.name == "NoldeLauncher-Setup-0.3.1.exe" and saved.read_bytes() == body


def test_install_uses_silent_in_place_upgrade_without_a_shell(tmp_path):
    args = installer_arguments(tmp_path / "setup.exe")
    assert args[0].endswith("setup.exe")
    for flag in ("/SILENT", "/NORESTART", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"):
        assert flag in args


# ----- repository link and welcome -----

def test_repository_button_sits_next_to_the_website_button(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("NOLDE_DATA_DIR", str(tmp_path / "d"))
    from nolde_launcher.app import context
    from nolde_launcher.services.catalog_service import CatalogSnapshot
    from nolde_launcher.ui.main_window import MainWindow
    import time
    win = MainWindow(context.build_services(), CatalogSnapshot((), "network", time.time(), 0), "")
    repo = [b for b in win.sidebar.findChildren(QToolButton) if b.objectName() == "RepoButton"]
    site = [b for b in win.sidebar.findChildren(QToolButton) if b.objectName() == "SiteButton"]
    assert len(repo) == 1 and len(site) == 1
    assert repo[0].toolTip() == "GitHub repository"
    assert REPO_URL == "https://github.com/NoldeTeam/nolde-launcher"
    win.close()


def test_welcome_is_marked_seen_and_not_shown_again(tmp_path, monkeypatch):
    monkeypatch.setenv("NOLDE_DATA_DIR", str(tmp_path / "d"))
    from nolde_launcher.storage.settings import SettingsService
    svc = SettingsService(tmp_path / "s.json")
    assert svc.settings.welcome_seen is False
    svc.update(welcome_seen=True)
    assert SettingsService(tmp_path / "s.json").settings.welcome_seen is True


def test_welcome_dialog_has_the_early_access_text(qapp):
    from nolde_launcher.localization.i18n import t
    assert "Early Access" in VERSION_LABEL
    assert "new versions" in t("welcome.body_updates").lower()
    assert t("welcome.repository")
