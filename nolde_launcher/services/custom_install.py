"""Steps that run after a managed user-added app is installed: copy its files, then install its mods.

Mods are installed from their GitHub repositories with the same release rules as games. A mod
that fails does not stop the game install; the failures are returned so the user is told.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..models.project import CatalogProject
from .download_manager import DownloadError, download_to_file
from .install_manager import InstallError, extract_archive, resolve_inside, validate_archive
from .release_service import ReleaseError, parse_github_repo


def finish_custom_install(install_dir: Path, project: CatalogProject, provider,
                          work_dir: Path, session=None) -> list[str]:
    """Copy the user's files and install the mods. Returns a list of problems (empty when all is well)."""
    for source in project.files_to_add:
        target = resolve_inside(install_dir, Path(source).name)
        shutil.copy2(source, target)

    problems: list[str] = []
    if not (project.mod_sources and project.mods_path):
        return problems
    work_dir.mkdir(parents=True, exist_ok=True)
    mods_root = resolve_inside(install_dir, project.mods_path)
    mods_root.mkdir(parents=True, exist_ok=True)
    for url in project.mod_sources:
        owner_repo = parse_github_repo(url)
        name = owner_repo[1] if owner_repo else url
        try:
            build = provider.resolve(url)
            if build.asset is None:
                raise InstallError("no Windows build is published")
            archive = download_to_file(build.asset.download_url, work_dir / f"mod-{name}.zip",
                                       session=session, expected_sha256=build.asset.sha256 or None)
            members = validate_archive(archive)
            target = resolve_inside(mods_root, name) if project.mods_own_folder else mods_root
            extract_archive(archive, target, members)
            archive.unlink(missing_ok=True)
        except (InstallError, ReleaseError, DownloadError, OSError) as exc:
            problems.append(f"{name}: {exc}")
    return problems
