"""Decide what the primary action for a catalog project should be.

The catalog only describes a project. Whether a compatible build can actually be
downloaded is decided here, per project, from verified sources listed in the
catalog. The result drives the button label in the UI:

- INSTALL:      a verified provider returned a Windows build.
- OPEN_PAGE:    no integrated build, but an official project page exists.
- UNAVAILABLE:  neither a build nor a project page is available.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..models.project import CatalogProject
from .release_service import ReleaseError, ResolvedBuild


class PrimaryAction(Enum):
    INSTALL = "install"
    OPEN_PAGE = "open_page"
    UNAVAILABLE = "unavailable"
    MANUAL = "manual"              # a user-added app whose files the user places by hand


@dataclass(frozen=True)
class Availability:
    action: PrimaryAction
    reason_key: str = ""           # translation key explaining the state
    reason_args: tuple[tuple[str, str], ...] = ()
    build: ResolvedBuild | None = None
    page_url: str = ""

    @property
    def reason_arguments(self) -> dict[str, str]:
        return dict(self.reason_args)


class SourceResolver:
    def __init__(self, providers) -> None:
        self._providers = list(providers)

    def resolve(self, project: CatalogProject) -> Availability:
        if project.management == "manual":
            return Availability(PrimaryAction.MANUAL, reason_key="custom.manual_hint")
        page = project.project_page_url
        repo = project.repository_url

        if not repo:
            return self._fallback(page, "availability.reason_no_repo")

        provider = next((p for p in self._providers if p.supports(repo)), None)
        if provider is None:
            return self._fallback(page, "availability.gitlab_note")

        try:
            build = provider.resolve(repo, project.asset_filter) if project.asset_filter else provider.resolve(repo)
        except ReleaseError as exc:
            key = {
                "no_release": "availability.reason_no_release",
                "rate_limited": "availability.reason_rate_limited",
                "network": "availability.reason_network",
                "not_found": "availability.reason_not_found",
                "bad_response": "availability.reason_bad_response",
                "no_repo": "availability.reason_no_repo",
            }.get(exc.kind, "availability.reason_network")
            args = (("reason", str(exc)),) if key == "availability.reason_network" else ()
            return self._fallback(page, key, args)

        if build.asset is None:
            return self._fallback(page, "availability.reason_no_asset",
                                  (("reason", build.reason),), build)
        return Availability(PrimaryAction.INSTALL, build=build, page_url=page)

    @staticmethod
    def _fallback(page: str, reason_key: str, reason_args=(), build=None) -> Availability:
        if page:
            return Availability(PrimaryAction.OPEN_PAGE, reason_key, tuple(reason_args),
                                build, page)
        return Availability(PrimaryAction.UNAVAILABLE, reason_key, tuple(reason_args), build, "")


def static_hint(project: CatalogProject) -> str:
    """Cheap, offline hint for cards before a live check has run."""
    if project.repository_url and project.releases_url:
        return "availability.build_possible"
    return "availability.page_only"
