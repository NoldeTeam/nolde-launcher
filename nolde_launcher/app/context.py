"""Builds the service graph once at startup. UI code receives this object."""

from __future__ import annotations

from dataclasses import dataclass

from ..services.catalog_service import CatalogService, make_cache_store
from ..services.launch_manager import LaunchManager
from ..services.library_service import LibraryService, make_library_store
from ..services.release_service import GitHubReleaseProvider
from ..services.source_resolver import SourceResolver
from ..storage.paths import cache_dir, user_data_dir
from ..storage.settings import SettingsService


@dataclass
class AppServices:
    settings: SettingsService
    catalog: CatalogService
    library: LibraryService
    resolver: SourceResolver
    launcher: LaunchManager


def build_services() -> AppServices:
    data = user_data_dir()
    settings = SettingsService(data / "settings.json")
    catalog = CatalogService(make_cache_store(cache_dir() / "catalog.json"))
    library = LibraryService(make_library_store(data / "library.json"), settings.library_dir)
    resolver = SourceResolver([GitHubReleaseProvider()])
    return AppServices(settings, catalog, library, resolver, LaunchManager())
