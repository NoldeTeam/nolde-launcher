"""Discover: catalog search, filters, sorting and the virtualised card grid."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
                               QWidget)

from ..localization.i18n import t
from ..services.catalog_service import CatalogSnapshot, distinct_values, filter_projects
from ..services.source_resolver import static_hint
from .card_grid import CardGrid
from .widgets import GameCard, card_width, status_label_key

SORT_LABELS = (("name", "discover.sort_name"), ("updated", "discover.sort_updated"),
               ("progress", "discover.sort_progress"))


def sort_projects(projects, how: str):
    if how == "updated":  # ISO dates sort correctly as text; newest first, unknown last
        return sorted(projects, key=lambda p: p.last_updated or "", reverse=True)
    if how == "progress":
        return sorted(projects, key=lambda p: (p.progress is None, -(p.progress or 0)))
    return sorted(projects, key=lambda p: p.game_title.casefold())


class DiscoverPage(QWidget):
    open_project = Signal(str)
    refresh_requested = Signal()
    add_requested = Signal()

    def __init__(self, services, parent=None) -> None:
        super().__init__(parent)
        self._services = services
        self._projects: list = []
        self._by_id: dict[str, object] = {}
        self.installed_only = False
        self.images = None  # set by the main window once the image cache exists

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 18)
        root.setSpacing(14)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel(t("nav.discover"))
        title.setObjectName("PageTitle")
        titles.addWidget(title)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        titles.addWidget(self.count_label)
        header.addLayout(titles, 1)
        self.add_btn = QPushButton(t("custom.add_button"))
        self.add_btn.clicked.connect(self.add_requested.emit)
        header.addWidget(self.add_btn)
        self.refresh_btn = QPushButton(t("discover.refresh"))
        header.addWidget(self.refresh_btn)
        root.addLayout(header)

        self.banner = QLabel("")
        self.banner.setObjectName("Banner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        root.addWidget(self.banner)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.search = QLineEdit()
        self.search.setMinimumWidth(200)
        self.search.setPlaceholderText(t("discover.search_placeholder"))
        self.search.setClearButtonEnabled(True)
        controls.addWidget(self.search, 3)
        self.type_box = self._combo(t("discover.filter_type"))
        self.platform_box = self._combo(t("discover.filter_platform"))
        self.status_box = self._combo(t("discover.filter_status"))
        self.sort_box = QComboBox()
        self.sort_box.setMinimumWidth(120)
        for key, label_key in SORT_LABELS:
            self.sort_box.addItem(t(label_key), key)
        self.sort_box.setCurrentIndex(max(0, self.sort_box.findData(self._display().discover_sort)))
        for box in (self.type_box, self.platform_box, self.status_box, self.sort_box):
            controls.addWidget(box, 1)
        root.addLayout(controls)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(160)
        self._debounce.timeout.connect(self._apply)
        self.search.textChanged.connect(lambda _: self._debounce.start())
        for box in (self.type_box, self.platform_box, self.status_box):
            box.currentIndexChanged.connect(lambda _: self._apply())
        self.sort_box.currentIndexChanged.connect(self._sort_changed)
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)

        self.grid = CardGrid(t("discover.empty"), card_width(self._display().card_size))
        root.addWidget(self.grid, 1)
        root.addWidget(self.grid.empty)

    def _display(self):
        return self._services.settings.settings

    def _combo(self, placeholder: str) -> QComboBox:
        box = QComboBox()
        box.setMinimumWidth(120)
        box.addItem(placeholder, "")
        return box

    def _sort_changed(self) -> None:
        self._services.settings.update(discover_sort=self.sort_box.currentData())
        self._apply()

    def set_snapshot(self, snapshot: CatalogSnapshot | None, error: str = "") -> None:
        self._projects = list(snapshot.projects) if snapshot else []
        self._by_id = {p.id: p for p in self._projects}
        if snapshot and snapshot.source == "cache":
            when = (datetime.fromtimestamp(snapshot.fetched_at).strftime("%Y-%m-%d %H:%M")
                    if snapshot.fetched_at else "?")
            self.banner.setText(t("discover.offline_banner", when=when))
            self.banner.show()
        elif error:
            self.banner.setText(t("discover.load_failed", reason=error))
            self.banner.show()
        else:
            self.banner.hide()
        self._fill(self.type_box, "project_types", t("discover.filter_type"))
        self._fill(self.platform_box, "platforms", t("discover.filter_platform"))
        self._fill(self.status_box, "status", t("discover.filter_status"))
        self._apply()

    def rebuild(self) -> None:
        """Called after appearance settings change: cards are rebuilt lazily."""
        self.grid.set_card_width(card_width(self._display().card_size))
        self.grid.refresh_all()

    def _fill(self, box: QComboBox, attr: str, placeholder: str) -> None:
        current = box.currentData()
        box.blockSignals(True)
        box.clear()
        box.addItem(placeholder, "")
        for value in distinct_values(self._projects, attr):
            box.addItem(t(f"status.{value}") if attr == "status" else value, value)
        box.setCurrentIndex(max(0, box.findData(current)))
        box.blockSignals(False)

    def _installed_ids(self) -> set[str]:
        return {r.project_id for r in self._services.library.records()}

    def _apply(self) -> None:
        projects = filter_projects(
            self._projects,
            query=self.search.text(),
            project_type=self.type_box.currentData() or "",
            status=self.status_box.currentData() or "",
            platform=self.platform_box.currentData() or "",
        )
        if self.installed_only:
            installed = self._installed_ids()
            projects = [p for p in projects if p.id in installed]
        projects = sort_projects(projects, self.sort_box.currentData() or "name")
        self.count_label.setText(t("discover.count", count=len(projects)))
        self.grid.set_entries([p.id for p in projects], self._make_card, binder=self._bind_card)

    def _make_card(self, project_id: str) -> GameCard:
        display = self._display()
        card = GameCard(project_id, "", "", width=card_width(display.card_size),
                        details=display.show_card_details)
        card.activated.connect(self.open_project.emit)
        self._bind_card(card, project_id)
        return card

    def _bind_card(self, card: GameCard, project_id: str) -> None:
        """Fill a card with a project's content. Used for new cards and for pooled ones."""
        project = self._by_id[project_id]
        display = self._display()
        badges = []
        if project.custom:
            badges.append((t("custom.badge"), "accent"))
        if project.status != "available":
            badges.append((t(status_label_key(project.status)), "default"))
        build_key = static_hint(project)
        short = {"availability.build_possible": "card.build_possible",
                 "availability.page_only": "card.page_only"}[build_key]
        badges.append((t(short), "success" if build_key == "availability.build_possible" else "default"))
        if project.project_types:
            badges.append((project.project_types[0].capitalize(), "accent"))
        if project.made_with_ai:
            badges.append((t("badge.made_with_ai"), "warning"))
        by = t("card.by", names=", ".join(project.authors[:2])) if project.authors else ""
        card.project_id = project.id
        card.title.setText(project.game_title)
        card.set_subtitle(by)
        card.set_description(project.description or project.long_description)
        card.replace_badges(tuple(badges[:3]))
        card.set_tags(tuple(project.platforms))
        card.set_details(display.show_card_details)
        self._apply_art(card, project)

    def _apply_art(self, card: GameCard, project) -> None:
        if self.images is None:
            return
        mode = self._display().grid_art
        cover = self.images.pixmap(project.cover_url) if project.cover_url else None
        logo = self.images.pixmap(project.logo_url) if project.logo_url else None
        card.set_art(cover, logo, mode)

    def refresh_card_covers(self) -> None:
        def update(project_id, card):
            project = self._by_id.get(project_id)
            if project is not None:
                self._apply_art(card, project)
        self.grid.for_each(update)
