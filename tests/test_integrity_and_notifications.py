"""Integrity records, verification, the installer script and the tray notifier."""

import os
import sys
from pathlib import Path

import pytest

from nolde_launcher.services import integrity
from nolde_launcher.services.integrity import (build_manifest, load_manifest, save_manifest,
                                               verify_install)


@pytest.fixture
def game(tmp_path, monkeypatch):
    monkeypatch.setenv("NOLDE_DATA_DIR", str(tmp_path / "data"))
    folder = tmp_path / "Library" / "Demo"
    (folder / "bin").mkdir(parents=True)
    (folder / "Demo.exe").write_bytes(b"MZ-original")
    (folder / "bin" / "data.pak").write_bytes(b"x" * 2000)
    return folder


def test_unchanged_install_verifies_ok(game):
    report = verify_install(game, build_manifest(game))
    assert report.ok and report.checked == 2 and report.extra_count == 0


def test_changed_file_is_reported(game):
    manifest = build_manifest(game)
    (game / "bin" / "data.pak").write_bytes(b"y" * 2000)  # same size, different content
    report = verify_install(game, manifest)
    assert not report.ok and report.changed == ["bin/data.pak"]


def test_missing_file_is_reported(game):
    manifest = build_manifest(game)
    (game / "Demo.exe").unlink()
    report = verify_install(game, manifest)
    assert not report.ok and report.missing == ["Demo.exe"]


def test_new_files_are_reported_but_do_not_fail_the_check(game):
    manifest = build_manifest(game)
    (game / "saves").mkdir()
    (game / "saves" / "slot1.sav").write_bytes(b"progress")
    report = verify_install(game, manifest)
    assert report.ok  # save files are normal
    assert report.extra == ["saves/slot1.sav"] and report.extra_count == 1


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need extra rights on Windows")
def test_symbolic_links_are_never_followed(game, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("not part of the game")
    os.symlink(outside, game / "link.txt")
    manifest = build_manifest(game)
    assert "link.txt" not in manifest["files"]


def test_manifest_is_stored_outside_the_game_folder(game, tmp_path):
    save_manifest("demo", build_manifest(game))
    stored = integrity.manifest_path("demo")
    assert not str(stored).startswith(str(game))
    assert load_manifest("demo")["files"]["Demo.exe"]["size"] == len(b"MZ-original")


def test_damaged_manifest_is_treated_as_missing(game):
    integrity.manifest_path("bad").write_text("{not json")
    assert load_manifest("bad") is None


def test_verification_counts_are_complete_even_when_the_list_is_capped(game):
    manifest = build_manifest(game)
    for i in range(integrity.REPORT_LIMIT + 5):
        (game / f"new{i}.txt").write_bytes(b"n")
    report = verify_install(game, manifest)
    assert report.extra_count == integrity.REPORT_LIMIT + 5
    assert len(report.extra) == integrity.REPORT_LIMIT


# ----- installer script -----

INSTALLER = Path(__file__).resolve().parents[1] / "packaging" / "installer" / "NoldeLauncher.iss"


def test_installer_script_installs_per_user_without_admin_rights():
    text = INSTALLER.read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in text
    assert "{localappdata}" in text
    assert "NoldeLauncher.exe" in text


def test_installer_packages_the_pyinstaller_output_and_creates_shortcuts():
    text = INSTALLER.read_text(encoding="utf-8")
    assert r"..\..\dist\NoldeLauncher\*" in text
    assert "[Icons]" in text and r"{group}" in text
    assert "{uninstallexe}" in text


def test_uninstall_keeps_user_data_unless_the_user_asks():
    text = INSTALLER.read_text(encoding="utf-8")
    # Deletion happens only inside the IDYES branch of a default-No question.
    assert "MB_DEFBUTTON2" in text
    yes_branch = text.split("= IDYES then", 1)
    assert len(yes_branch) == 2 and "DelTree(DataDir" in yes_branch[1].split("end;", 1)[0]


# ----- notifier -----

def test_notifier_does_nothing_without_a_system_tray(qapp, monkeypatch):
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QMainWindow, QSystemTrayIcon
    from nolde_launcher.ui.notifier import Notifier
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: False))
    window = QMainWindow()
    notifier = Notifier(QIcon(), window, lambda: True)
    assert notifier.available is False
    assert notifier.notify("Title", "Body") is False  # no tray: skipped without error
    notifier.set_enabled(False)  # also safe
