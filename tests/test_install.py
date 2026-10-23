import hashlib

import pytest

from nolde_launcher.services.install_manager import (
    InstallError, install_archive, is_safe_folder_name, resolve_inside,
)
from tests.helpers import make_zip


def build_zip(tmp_path, entries, symlinks=None, name="build.zip"):
    return make_zip(tmp_path / name, entries, symlinks)


def test_valid_archive_installs_and_lists_executables(tmp_path):
    archive = build_zip(tmp_path, {
        "Game/readme.txt": b"hi",
        "Game/bin/game.exe": b"MZ",
        "Game/Launcher.exe": b"MZ",
    })
    library = tmp_path / "library"
    result = install_archive(archive, library, "Demo")
    assert result.install_dir == library / "Demo"
    assert (library / "Demo" / "Game" / "bin" / "game.exe").exists()
    assert result.executables == ("Game/Launcher.exe", "Game/bin/game.exe")  # shallowest first
    assert not any(p.name.startswith(".staging") for p in library.iterdir())


def test_zip_slip_is_rejected_and_nothing_escapes(tmp_path):
    archive = build_zip(tmp_path, {"../../escaped.txt": b"pwned", "ok.txt": b"x"})
    library = tmp_path / "library"
    with pytest.raises(InstallError) as info:
        install_archive(archive, library, "Demo")
    assert info.value.kind == "unsafe_archive"
    assert not (tmp_path / "escaped.txt").exists()
    assert not (library / "Demo").exists()
    assert not any(p.name.startswith(".staging") for p in library.iterdir()) if library.exists() else True


@pytest.mark.parametrize("member", ["/etc/passwd", "C:/Windows/evil.exe", "C:evil.exe",
                                    "a/../../b.txt", "..\\..\\win.ini"])
def test_malicious_member_paths_are_rejected(tmp_path, member):
    archive = build_zip(tmp_path, {member: b"x"})
    with pytest.raises(InstallError):
        install_archive(archive, tmp_path / "library", "Demo")


def test_symbolic_links_are_rejected(tmp_path):
    archive = build_zip(tmp_path, {"ok.txt": b"x"}, symlinks={"link": "/etc/passwd"})
    with pytest.raises(InstallError, match="symbolic links"):
        install_archive(archive, tmp_path / "library", "Demo")


def test_non_zip_file_is_reported_as_bad_archive(tmp_path):
    bogus = tmp_path / "fake.zip"
    bogus.write_bytes(b"this is not a zip")
    with pytest.raises(InstallError) as info:
        install_archive(bogus, tmp_path / "library", "Demo")
    assert info.value.kind == "bad_archive"


def test_existing_installation_requires_overwrite_confirmation(tmp_path):
    library = tmp_path / "library"
    archive = build_zip(tmp_path, {"v1.txt": b"1"})
    install_archive(archive, library, "Demo")
    with pytest.raises(InstallError) as info:
        install_archive(build_zip(tmp_path, {"v2.txt": b"2"}, name="v2.zip"), library, "Demo")
    assert info.value.kind == "exists"
    assert (library / "Demo" / "v1.txt").exists()  # untouched


def test_overwrite_replaces_previous_installation(tmp_path):
    library = tmp_path / "library"
    install_archive(build_zip(tmp_path, {"v1.txt": b"1"}), library, "Demo")
    install_archive(build_zip(tmp_path, {"v2.txt": b"2"}, name="v2.zip"), library, "Demo", overwrite=True)
    assert (library / "Demo" / "v2.txt").exists()
    assert not (library / "Demo" / "v1.txt").exists()
    assert not any(p.name.startswith(".replaced") for p in library.iterdir())


def test_hash_mismatch_stops_before_extraction(tmp_path):
    archive = build_zip(tmp_path, {"a.txt": b"a"})
    with pytest.raises(InstallError) as info:
        install_archive(archive, tmp_path / "library", "Demo", expected_sha256="f" * 64)
    assert info.value.kind == "hash_mismatch"
    assert not (tmp_path / "library" / "Demo").exists()


def test_correct_hash_passes(tmp_path):
    archive = build_zip(tmp_path, {"a.txt": b"a"})
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    result = install_archive(archive, tmp_path / "library", "Demo", expected_sha256=digest)
    assert (result.install_dir / "a.txt").exists()


def test_unsafe_install_folder_names_are_refused(tmp_path):
    archive = build_zip(tmp_path, {"a.txt": b"a"})
    for name in ["../escape", "..", ".", "a/b", "", "CON.", ".hidden"]:
        with pytest.raises(InstallError):
            install_archive(archive, tmp_path / "library", name)
    assert is_safe_folder_name("Super Mario World Recomp")


def test_resolve_inside_blocks_escape_and_accepts_nested(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    assert resolve_inside(root, "a/b/c.exe") == (root / "a" / "b" / "c.exe").resolve()
    for bad in ["../x", "a/../../x", "/abs", "C:/x", "a\x00b", ""]:
        with pytest.raises(InstallError):
            resolve_inside(root, bad)


def test_failed_install_keeps_unrelated_library_content(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    (library / "UserNotes").mkdir()
    (library / "UserNotes" / "save.txt").write_text("keep me")
    with pytest.raises(InstallError):
        install_archive(build_zip(tmp_path, {"../x": b"1"}), library, "Demo")
    assert (library / "UserNotes" / "save.txt").read_text() == "keep me"
