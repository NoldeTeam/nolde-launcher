"""Installed-game records. Stored as relative paths so the library folder can move."""

from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..storage.json_store import JsonStore
from .install_manager import InstallError, resolve_inside

LIBRARY_SCHEMA_VERSION = 1


@dataclass
class InstallRecord:
    project_id: str
    game_title: str
    project_name: str
    install_folder: str            # relative to library dir
    main_executable: str           # relative to install folder
    platform: str = "Windows"
    installed_version: str = ""
    source_provider: str = ""
    source_url: str = ""
    installed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    state: str = "installed"       # installed | needs_setup
    sha256: str = ""
    launch_args: list[str] = field(default_factory=list)
    first_run_confirmed: bool = False  # user has approved starting this build once
    last_played_at: str = ""           # ISO timestamp of the last successful launch
    play_seconds: int = 0              # total time the game has been running

    @classmethod
    def from_dict(cls, raw: dict) -> "InstallRecord":
        args = raw.get("launch_args") or []
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            args = []
        return cls(
            project_id=str(raw["project_id"]),
            game_title=str(raw.get("game_title", "")),
            project_name=str(raw.get("project_name", "")),
            install_folder=str(raw["install_folder"]),
            main_executable=str(raw.get("main_executable", "")),
            platform=str(raw.get("platform", "Windows")),
            installed_version=str(raw.get("installed_version", "")),
            source_provider=str(raw.get("source_provider", "")),
            source_url=str(raw.get("source_url", "")),
            installed_at=str(raw.get("installed_at", "")),
            state=str(raw.get("state", "installed")),
            sha256=str(raw.get("sha256", "")),
            launch_args=args,
            first_run_confirmed=raw.get("first_run_confirmed") is True,
            last_played_at=str(raw.get("last_played_at", "")),
            play_seconds=max(0, int(raw.get("play_seconds", 0) or 0)),
        )


class LibraryService:
    def __init__(self, store: JsonStore, library_dir: Path) -> None:
        self._store = store
        self.library_dir = Path(library_dir)
        self._records: dict[str, InstallRecord] = {}
        self._load()

    def _load(self) -> None:
        raw = self._store.load()
        for item in raw.get("installs", []):
            try:
                record = InstallRecord.from_dict(item)
                # Reject records whose paths would not validate; they cannot be launched.
                resolve_inside(self.library_dir, record.install_folder)
            except (KeyError, TypeError, InstallError):
                continue
            self._records[record.project_id] = record

    def _save(self) -> None:
        self._store.save({"installs": [asdict(r) for r in self.records()]})

    def records(self) -> list[InstallRecord]:
        return sorted(self._records.values(), key=lambda r: r.game_title.casefold())

    def get(self, project_id: str) -> InstallRecord | None:
        return self._records.get(project_id)

    def add_or_replace(self, record: InstallRecord) -> None:
        resolve_inside(self.library_dir, record.install_folder)
        self._records[record.project_id] = record
        self._save()

    def set_main_executable(self, project_id: str, relative_exe: str) -> None:
        record = self._records[project_id]
        record.main_executable = relative_exe
        record.state = "installed"
        self._save()

    def confirm_first_run(self, project_id: str) -> None:
        record = self._records[project_id]
        record.first_run_confirmed = True
        self._save()

    def add_playtime(self, project_id: str, seconds: float) -> None:
        record = self._records.get(project_id)
        if record is None or seconds <= 0:
            return
        record.play_seconds += int(seconds)
        self._save()

    def mark_played(self, project_id: str) -> None:
        record = self._records.get(project_id)
        if record is None:
            return
        record.last_played_at = datetime.now(timezone.utc).isoformat()
        self._save()

    def install_dir(self, record: InstallRecord) -> Path:
        return resolve_inside(self.library_dir, record.install_folder)

    def verify(self, project_id: str) -> list[str]:
        """Return a list of problems. Only the main executable's presence is checked,
        because no integrity manifest is published for most projects."""
        record = self._records.get(project_id)
        if record is None:
            return ["not installed"]
        problems = []
        install_dir = self.install_dir(record)
        if not install_dir.is_dir():
            problems.append("installation folder is missing")
            return problems
        try:
            exe = resolve_inside(install_dir, record.main_executable)
            if not exe.is_file():
                problems.append("main executable is missing")
        except InstallError:
            problems.append("main executable path is invalid")
        return problems

    def uninstall(self, project_id: str) -> None:
        """Delete only the launcher-managed installation folder inside the library."""
        record = self._records.get(project_id)
        if record is None:
            return
        install_dir = self.install_dir(record)
        library_root = self.library_dir.resolve()
        if install_dir == library_root or install_dir.parent != library_root:
            raise InstallError("refusing to delete a folder outside the library root", kind="unsafe_archive")
        if install_dir.exists():
            shutil.rmtree(install_dir)
        del self._records[project_id]
        self._save()

    def forget(self, project_id: str) -> None:
        """Remove the record without touching files (used when the user keeps files)."""
        if self._records.pop(project_id, None) is not None:
            self._save()


def make_library_store(path) -> JsonStore:
    return JsonStore(path, LIBRARY_SCHEMA_VERSION, lambda: {"installs": []})
