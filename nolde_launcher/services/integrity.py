"""Integrity manifests for installed games.

A manifest lists every file of an installed game with its size and SHA-256, and is written
right after installation. Verification compares the folder with that list:

- missing: a file from the manifest no longer exists
- changed: a file exists but its size or hash differs
- extra:   a file that was not in the manifest (for example a save file the game created).
           Extra files are reported separately because they are normal.

The manifest lives in the launcher's data folder, not inside the game folder, so it cannot
be changed by the same files it protects. It does not prove the original download was
correct; it proves the installed files have not changed since installation.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..storage.paths import user_data_dir

MANIFEST_VERSION = 1
CHUNK = 1024 * 1024
REPORT_LIMIT = 50  # file names returned to the UI; the counts are always complete


def manifests_dir() -> Path:
    path = user_data_dir() / "manifests"
    path.mkdir(parents=True, exist_ok=True)
    return path


def manifest_path(project_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_id)
    return manifests_dir() / f"{safe}.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _files(root: Path):
    """Yield (relative posix path, absolute path) for regular files. Symlinks are skipped
    so the check never follows a link out of the game folder."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
        for name in filenames:
            full = Path(dirpath) / name
            if full.is_symlink() or not full.is_file():
                continue
            yield full.relative_to(root).as_posix(), full


def build_manifest(install_dir: Path) -> dict:
    files = {}
    for rel, full in _files(install_dir):
        files[rel] = {"size": full.stat().st_size, "sha256": _sha256(full)}
    return {"version": MANIFEST_VERSION, "created": time.time(), "files": files}


def save_manifest(project_id: str, manifest: dict) -> None:
    path = manifest_path(project_id)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def load_manifest(project_id: str) -> dict | None:
    path = manifest_path(project_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        return None
    return data


def delete_manifest(project_id: str) -> None:
    manifest_path(project_id).unlink(missing_ok=True)


@dataclass
class VerifyReport:
    checked: int = 0
    missing: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    missing_count: int = 0
    changed_count: int = 0
    extra_count: int = 0

    @property
    def ok(self) -> bool:
        return self.missing_count == 0 and self.changed_count == 0

    def _add(self, bucket: list[str], name: str, counter: str) -> None:
        setattr(self, counter, getattr(self, counter) + 1)
        if len(bucket) < REPORT_LIMIT:
            bucket.append(name)


def verify_install(install_dir: Path, manifest: dict) -> VerifyReport:
    report = VerifyReport()
    expected: dict = manifest.get("files", {})
    present = dict(_files(install_dir))
    for rel, info in expected.items():
        report.checked += 1
        full = present.get(rel)
        if full is None:
            report._add(report.missing, rel, "missing_count")
            continue
        if full.stat().st_size != info.get("size") or _sha256(full) != info.get("sha256"):
            report._add(report.changed, rel, "changed_count")
    for rel in present:
        if rel not in expected:
            report._add(report.extra, rel, "extra_count")
    return report
