"""Coordinates download -> verify -> install -> library record, for new installs and updates.

Each step is separate. Nothing is executed here: installation only extracts. The first run is
a separate, explicitly confirmed action in the Library.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from ..localization.i18n import t
from ..models.project import CatalogProject
from ..services.download_manager import DownloadManager, DownloadStatus, DownloadTask
from ..services.install_manager import InstallError, install_archive
from ..services.install_naming import download_file_name, folder_name_for
from ..services.library_service import InstallRecord
from ..services.release_service import ResolvedBuild
from .workers import run_async

log = logging.getLogger("nolde.install")


class InstallController(QObject):
    status_changed = Signal(str, str)     # project_id, message
    finished_ok = Signal(str, str)        # project_id, message
    finished_error = Signal(str, str)     # project_id, message
    library_changed = Signal()

    def __init__(self, services, choose_executable, parent=None) -> None:
        super().__init__(parent)
        self._services = services
        self._choose_executable = choose_executable  # callable(list[str]) -> str | None
        self.downloads = DownloadManager(parent=self)
        self._pending: dict[int, tuple[CatalogProject, ResolvedBuild, bool]] = {}
        self._requests: dict[str, tuple[CatalogProject, ResolvedBuild]] = {}
        self.downloads.task_changed.connect(self._on_task_changed)

    def is_busy(self, project_id: str) -> bool:
        return any(p.id == project_id for p, _, _ in self._pending.values())

    def retry(self, project_id: str) -> bool:
        request = self._requests.get(project_id)
        if request is None or self.is_busy(project_id):
            return False
        project, build = request
        if self._services.library.get(project_id) is not None:
            self._begin(project, build, updating=True)  # a failed update retries as an update
        else:
            self._begin(project, build, updating=False)
        return True

    def start(self, project: CatalogProject, build: ResolvedBuild) -> None:
        if self._services.library.get(project.id) is not None:
            self.finished_error.emit(project.id, t("install.exists"))
            return
        self._begin(project, build, updating=False)

    def update(self, project: CatalogProject, build: ResolvedBuild) -> None:
        """Install a newer build over the existing game, keeping its library record."""
        if self._services.library.get(project.id) is None:
            self.finished_error.emit(project.id, t("install.failed", reason="not installed"))
            return
        self._begin(project, build, updating=True)

    def _begin(self, project: CatalogProject, build: ResolvedBuild, updating: bool) -> None:
        self._requests[project.id] = (project, build)
        asset = build.asset
        if asset is None:
            self.finished_error.emit(project.id, t("error.unexpected", reason="no asset"))
            return
        task = self.downloads.enqueue(
            project.id, asset.download_url,
            self._services.settings.download_dir / download_file_name(project, asset.name),
            expected_sha256=asset.sha256 or None,
        )
        self._pending[task.task_id] = (project, build, updating)
        self.status_changed.emit(project.id, t("install.downloading"))

    def _on_task_changed(self, task: DownloadTask) -> None:
        entry = self._pending.get(task.task_id)
        if entry is None:
            return
        project, build, updating = entry
        if task.status is DownloadStatus.COMPLETED:
            del self._pending[task.task_id]
            self.status_changed.emit(project.id, t("install.extracting"))
            run_async(self._install_job, project, build, task.destination, updating,
                      on_ok=lambda result: self._on_installed(project, build, result, updating),
                      on_err=lambda exc: self._on_error(project, build, exc),
                      parent=self)
        elif task.status is DownloadStatus.CANCELLED:
            del self._pending[task.task_id]
            self.finished_error.emit(project.id, t("downloads.status_cancelled"))
        elif task.status is DownloadStatus.FAILED:
            del self._pending[task.task_id]
            self.finished_error.emit(project.id, t("install.failed", reason=task.error))
        # PAUSED keeps the entry: the same task resumes later and reaches one of the states above.

    def _install_job(self, project: CatalogProject, build: ResolvedBuild, archive: Path, updating: bool):
        folder = folder_name_for(project)
        # The archive's hash was verified during download when GitHub published one.
        return install_archive(archive, self._services.settings.library_dir, folder,
                               overwrite=updating)

    def _on_installed(self, project: CatalogProject, build: ResolvedBuild, result, updating: bool) -> None:
        try:
            self._archive_for(project, build).unlink(missing_ok=True)
        except OSError:
            pass
        previous = self._services.library.get(project.id) if updating else None
        exe, state = self._pick_executable(result.executables, previous)
        if previous is not None:
            record = replace(previous, installed_version=build.release.tag,
                             source_provider=build.provider, source_url=build.release.html_url,
                             sha256=build.asset.sha256 if build.asset else "",
                             main_executable=exe, state=state,
                             installed_at=_now_iso())
            message = t("install.updated", name=project.project_name, version=build.release.tag or "—")
        else:
            record = InstallRecord(
                project_id=project.id, game_title=project.game_title,
                project_name=project.project_name, install_folder=result.folder_name,
                main_executable=exe, platform="Windows", installed_version=build.release.tag,
                source_provider=build.provider, source_url=build.release.html_url,
                state=state, sha256=build.asset.sha256 if build.asset else "",
            )
            message = (t("install.no_exe") if state == "needs_setup"
                       else t("install.done", name=project.project_name))
        self._services.library.add_or_replace(record)
        log.info("%s %s version %s (state=%s)", "updated" if updating else "installed",
                 project.id, build.release.tag, state)
        self.library_changed.emit()
        self.finished_ok.emit(project.id, message)

    def _pick_executable(self, executables, previous) -> tuple[str, str]:
        if not executables:
            return "", "needs_setup"
        if previous is not None and previous.main_executable in executables:
            return previous.main_executable, "installed"  # keep the user's choice
        if len(executables) == 1:
            return executables[0], "installed"
        chosen = self._choose_executable(list(executables))
        return (chosen or executables[0]), "installed"

    def _on_error(self, project: CatalogProject, build: ResolvedBuild, exc: Exception) -> None:
        log.warning("install failed for %s: %s", project.id, exc.__class__.__name__)
        try:
            self._archive_for(project, build).unlink(missing_ok=True)
        except OSError:
            pass
        if isinstance(exc, InstallError) and exc.kind == "exists":
            message = t("install.exists")
        elif isinstance(exc, InstallError):
            message = t("install.failed", reason=str(exc))
        else:
            message = t("install.failed", reason=exc.__class__.__name__)
        self.finished_error.emit(project.id, message)

    def _archive_for(self, project: CatalogProject, build: ResolvedBuild) -> Path:
        return self._services.settings.download_dir / download_file_name(project, build.asset.name)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
