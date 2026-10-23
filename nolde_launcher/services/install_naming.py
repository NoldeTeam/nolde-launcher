"""Stable, filesystem-safe folder names derived from catalog identifiers."""

import hashlib
import re

from ..models.project import CatalogProject
from .install_manager import is_safe_folder_name


def folder_name_for(project: CatalogProject) -> str:
    for candidate in (project.slug, project.id):
        if candidate and is_safe_folder_name(candidate):
            return candidate
    digest = hashlib.sha256(project.id.encode("utf-8")).hexdigest()[:12]
    return f"project-{digest}"


def download_file_name(project: CatalogProject, asset_name: str) -> str:
    safe_asset = re.sub(r"[^A-Za-z0-9._-]", "_", asset_name)[:120] or "build.zip"
    return f"{folder_name_for(project)}-{safe_asset}"
