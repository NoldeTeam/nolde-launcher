import sys

import pytest

from nolde_launcher.services.install_manager import InstallError
from nolde_launcher.services.launch_manager import (
    AlreadyRunningError, LaunchError, LaunchManager, LaunchRequest, resolve_executable,
)
from nolde_launcher.services.library_service import InstallRecord, LibraryService, make_library_store
from nolde_launcher.storage.json_store import JsonStore

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX shell script as the test program")


def make_program(install_dir, rel, body):
    path = install_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def make_record(library, folder="Demo", exe="demo.sh", pid="demo"):
    return InstallRecord(project_id=pid, game_title="Demo Game", project_name="Demo Project",
                         install_folder=folder, main_executable=exe)


# ---------- launching ----------

@posix_only
def test_harmless_test_program_launches_from_install_dir(tmp_path):
    library = tmp_path / "library"
    install = library / "Demo"
    marker = tmp_path / "ran.txt"
    make_program(install, "demo.sh", f"#!/bin/sh\npwd > '{marker}'\nexit 0\n")
    proc = LaunchManager().launch(library, LaunchRequest("demo", "Demo", "demo.sh"))
    assert proc.wait(timeout=10) == 0
    assert marker.read_text().strip() == str(install.resolve())  # working dir is the game folder


@posix_only
def test_duplicate_launch_is_prevented_while_running(tmp_path):
    library = tmp_path / "library"
    make_program(library / "Demo", "demo.sh", "#!/bin/sh\nsleep 2\n")
    manager = LaunchManager()
    request = LaunchRequest("demo", "Demo", "demo.sh")
    manager.launch(library, request)
    with pytest.raises(AlreadyRunningError):
        manager.launch(library, request)


def test_missing_executable_reports_clearly(tmp_path):
    library = tmp_path / "library"
    (library / "Demo").mkdir(parents=True)
    with pytest.raises(LaunchError, match="was not found"):
        resolve_executable(library, LaunchRequest("demo", "Demo", "gone.exe"))


def test_missing_install_folder_reports_clearly(tmp_path):
    with pytest.raises(LaunchError, match="installation folder is missing"):
        resolve_executable(tmp_path, LaunchRequest("demo", "Nope", "x.exe"))


@pytest.mark.parametrize("exe", ["../../evil", "/bin/sh", "C:/evil.exe"])
def test_executable_paths_cannot_escape_install_folder(tmp_path, exe):
    library = tmp_path / "library"
    (library / "Demo").mkdir(parents=True)
    with pytest.raises(LaunchError):
        resolve_executable(library, LaunchRequest("demo", "Demo", exe))


def test_launch_uses_argument_list_not_shell(tmp_path, monkeypatch):
    library = tmp_path / "library"
    make_program(library / "Demo", "game.exe" if sys.platform == "win32" else "game", "x")
    captured = {}

    class FakeProc:
        def poll(self):
            return None

    def fake_popen(args, **kwargs):
        captured.update(args=args, **kwargs)
        return FakeProc()

    monkeypatch.setattr("nolde_launcher.services.launch_manager.subprocess.Popen", fake_popen)
    monkeypatch.setattr("nolde_launcher.services.launch_manager.os.access", lambda *a: True)
    name = "game.exe" if sys.platform == "win32" else "game"
    LaunchManager().launch(library, LaunchRequest("demo", "Demo", name, ("--fullscreen", "a b; rm -rf")))
    assert isinstance(captured["args"], list)
    assert captured["args"][-2:] == ["--fullscreen", "a b; rm -rf"]
    assert captured["shell"] is False


# ---------- library persistence and uninstall ----------

def test_records_survive_restart(tmp_path):
    library = tmp_path / "library"
    (library / "Demo").mkdir(parents=True)
    store_path = tmp_path / "library.json"
    svc = LibraryService(make_library_store(store_path), library)
    svc.add_or_replace(make_record(library))
    reopened = LibraryService(make_library_store(store_path), library)
    record = reopened.get("demo")
    assert record is not None and record.install_folder == "Demo" and record.main_executable == "demo.sh"


def test_library_survives_moving_the_library_folder(tmp_path):
    old = tmp_path / "old"
    (old / "Demo").mkdir(parents=True)
    store_path = tmp_path / "library.json"
    LibraryService(make_library_store(store_path), old).add_or_replace(make_record(old))
    new = tmp_path / "new"
    (new / "Demo").mkdir(parents=True)
    moved = LibraryService(make_library_store(store_path), new)
    assert moved.get("demo") is not None  # relative paths: records follow the new library folder


def test_corrupt_library_file_is_quarantined_not_fatal(tmp_path):
    store_path = tmp_path / "library.json"
    store_path.write_text("{ this is not json", encoding="utf-8")
    library = tmp_path / "library"
    svc = LibraryService(make_library_store(store_path), library)
    assert svc.records() == []
    backups = list(tmp_path.glob("library.json.corrupt-*"))
    assert len(backups) == 1


def test_records_with_unsafe_paths_are_dropped_on_load(tmp_path):
    store_path = tmp_path / "library.json"
    JsonStore(store_path, 1, lambda: {}).save({"installs": [
        {"project_id": "evil", "game_title": "E", "project_name": "E",
         "install_folder": "../../outside", "main_executable": "x.exe"},
        {"project_id": "good", "game_title": "G", "project_name": "G",
         "install_folder": "Good", "main_executable": "g.exe"},
    ]})
    svc = LibraryService(make_library_store(store_path), tmp_path / "library")
    assert [r.project_id for r in svc.records()] == ["good"]


def test_verify_reports_missing_executable(tmp_path):
    library = tmp_path / "library"
    (library / "Demo").mkdir(parents=True)
    svc = LibraryService(make_library_store(tmp_path / "l.json"), library)
    svc.add_or_replace(make_record(library))
    assert svc.verify("demo") == ["main executable is missing"]
    make_program(library / "Demo", "demo.sh", "x")
    assert svc.verify("demo") == []


def test_uninstall_deletes_only_the_managed_folder(tmp_path):
    library = tmp_path / "library"
    (library / "Demo" / "data").mkdir(parents=True)
    (library / "Demo" / "data" / "save.dat").write_text("x")
    (library / "Keep").mkdir()
    (library / "Keep" / "other.txt").write_text("precious")
    svc = LibraryService(make_library_store(tmp_path / "l.json"), library)
    svc.add_or_replace(make_record(library))
    svc.uninstall("demo")
    assert not (library / "Demo").exists()
    assert (library / "Keep" / "other.txt").exists()
    assert svc.get("demo") is None


def test_uninstall_refuses_to_delete_library_root(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    svc = LibraryService(make_library_store(tmp_path / "l.json"), library)
    record = InstallRecord("bad", "B", "B", install_folder=".", main_executable="x.exe")
    svc._records["bad"] = record  # bypass add_or_replace to simulate tampering
    with pytest.raises(InstallError):
        svc.uninstall("bad")
    assert library.exists()


def test_first_run_confirmation_persists(tmp_path):
    library = tmp_path / "library"
    (library / "Demo").mkdir(parents=True)
    path = tmp_path / "l.json"
    svc = LibraryService(make_library_store(path), library)
    svc.add_or_replace(make_record(library))
    assert svc.get("demo").first_run_confirmed is False
    svc.confirm_first_run("demo")
    assert LibraryService(make_library_store(path), library).get("demo").first_run_confirmed is True
