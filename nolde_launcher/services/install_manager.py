"""Install downloaded ZIP builds into the library, safely.

Installation never executes anything. It validates the archive, extracts into a
staging folder inside the library, rejects unsafe entries (absolute paths,
drive letters, "..", symlinks, oversized archives), and only then moves the
staging folder into place. Failures remove only the staging folder.
"""

from __future__ import annotations

import re
import shutil
import stat
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .download_manager import sha256_of

MAX_ENTRIES = 50_000
MAX_UNCOMPRESSED_BYTES = 16 * 1024 ** 3
MAX_COMPRESSION_RATIO = 500  # guard against zip bombs
_FOLDER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,79}$")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_COPY_BUFFER = 256 * 1024


class InstallError(RuntimeError):
    def __init__(self, message: str, kind: str = "failed") -> None:
        super().__init__(message)
        self.kind = kind  # failed | exists | bad_archive | unsafe_archive | hash_mismatch


@dataclass(frozen=True)
class InstallResult:
    install_dir: Path
    folder_name: str
    executables: tuple[str, ...]  # relative to install_dir, shallowest first


def is_safe_folder_name(name: str) -> bool:
    return bool(_FOLDER_RE.match(name)) and name not in {".", ".."} and not name.endswith(".")


def resolve_inside(root: Path, relative: str) -> Path:
    """Map a relative archive or record path to an absolute path under `root`,
    refusing anything that would escape it."""
    if not relative or "\x00" in relative:
        raise InstallError("empty or invalid path", kind="unsafe_archive")
    normalized = relative.replace("\\", "/")
    if normalized.startswith("/") or _DRIVE_RE.match(normalized):
        raise InstallError(f"absolute path refused: {relative!r}", kind="unsafe_archive")
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise InstallError(f"path traversal refused: {relative!r}", kind="unsafe_archive")
    root_resolved = Path(root).resolve()
    target = (root_resolved.joinpath(*parts)).resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise InstallError(f"path escapes install folder: {relative!r}", kind="unsafe_archive")
    return target


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK


def validate_archive(archive: Path) -> list[zipfile.ZipInfo]:
    """Inspect every member before extracting anything."""
    if not zipfile.is_zipfile(archive):
        raise InstallError("the downloaded file is not a valid ZIP archive", kind="bad_archive")
    with zipfile.ZipFile(archive) as zf:
        members = zf.infolist()
        if len(members) > MAX_ENTRIES:
            raise InstallError("archive contains too many entries", kind="unsafe_archive")
        total = 0
        for info in members:
            if _is_symlink(info):
                raise InstallError(f"symbolic links are not allowed: {info.filename!r}",
                                   kind="unsafe_archive")
            resolve_inside(Path("/__probe__"), info.filename)  # path checks only
            total += info.file_size
            if total > MAX_UNCOMPRESSED_BYTES:
                raise InstallError("archive is too large when extracted", kind="unsafe_archive")
            if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                raise InstallError("archive has a suspicious compression ratio", kind="unsafe_archive")
        bad = zf.testzip()
        if bad is not None:
            raise InstallError(f"archive is corrupt at {bad!r}", kind="bad_archive")
        return members


def extract_archive(archive: Path, destination: Path, members: list[zipfile.ZipInfo]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for info in members:
            target = resolve_inside(destination, info.filename)
            if info.is_dir() or info.filename.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, _COPY_BUFFER)


def find_executables(root: Path) -> tuple[str, ...]:
    """List candidate Windows executables. Nothing is run."""
    found = []
    for path in Path(root).rglob("*.exe"):
        if path.is_file() and not path.is_symlink():
            found.append(path.relative_to(root).as_posix())
    found.sort(key=lambda rel: (rel.count("/"), rel.casefold()))
    return tuple(found)


def install_archive(
    archive: Path,
    library_dir: Path,
    folder_name: str,
    *,
    expected_sha256: str | None = None,
    overwrite: bool = False,
) -> InstallResult:
    if not is_safe_folder_name(folder_name):
        raise InstallError("install folder name is not allowed", kind="unsafe_archive")
    archive = Path(archive)
    library_dir = Path(library_dir)
    library_dir.mkdir(parents=True, exist_ok=True)
    install_dir = resolve_inside(library_dir, folder_name)
    if install_dir.exists() and not overwrite:
        raise InstallError("a folder with this name already exists in the library", kind="exists")

    if expected_sha256 and sha256_of(archive) != expected_sha256.lower():
        raise InstallError("archive failed its SHA-256 check", kind="hash_mismatch")

    members = validate_archive(archive)
    staging = library_dir / f".staging-{uuid.uuid4().hex}"
    old_dir: Path | None = None
    try:
        extract_archive(archive, staging, members)
        executables = find_executables(staging)
        if install_dir.exists():
            old_dir = library_dir / f".replaced-{uuid.uuid4().hex}"
            install_dir.rename(old_dir)
        staging.rename(install_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if old_dir is not None and not install_dir.exists():
            old_dir.rename(install_dir)  # restore previous installation
        raise
    if old_dir is not None:
        shutil.rmtree(old_dir, ignore_errors=True)
    return InstallResult(install_dir=install_dir, folder_name=folder_name,
                         executables=executables)
