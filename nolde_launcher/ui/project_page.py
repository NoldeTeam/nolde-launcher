"""Project page: wide hero banner, About and Sources on the left, Info and Links on the right.

The live source check runs only when this page is opened, so browsing the catalog
never triggers a burst of GitHub API calls.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from ..localization.i18n import t
from .dialogs import ThemedMessage as QMessageBox
from ..models.project import CatalogProject
from ..services.source_resolver import Availability, PrimaryAction
from .icons import icon
from .theme import COLORS
from .widgets import badge, clear_layout, fade_in, initials, rounded, status_label_key
from .workers import run_async

HERO_HEIGHT = 300
HERO_RADIUS = 14


class HeroOverlay(QWidget):
    """Transparent layer with a bottom gradient so the title reads over any artwork."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        base = QColor(COLORS["bg"])
        clear = QColor(base)
        clear.setAlpha(0)
        mid = QColor(base)
        mid.setAlpha(170)
        bottom = QColor(base)
        bottom.setAlpha(245)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, clear)
        gradient.setColorAt(0.42, clear)
        gradient.setColorAt(0.78, mid)
        gradient.setColorAt(1.0, bottom)
        painter.fillRect(self.rect(), gradient)
        painter.end()


class HeroFrame(QFrame):
    """Banner: cover artwork as the background, the transparent logo on top, then text and action.

    The cover and the logo are separate catalog fields. When a logo exists it replaces the
    large title text, as in the reference design."""

    LOGO_MAX = QSize(460, 150)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("HeroFrame")
        self.setMinimumHeight(HERO_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._cover: QPixmap | None = None
        self._logo: QPixmap | None = None
        self._title = ""

        self.cover = QLabel(self)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overlay = HeroOverlay(self)

        layout = QVBoxLayout(self.overlay)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.addStretch(1)
        row = QHBoxLayout()
        row.setSpacing(20)
        text = QVBoxLayout()
        text.setSpacing(8)
        self.badge_row = QHBoxLayout()
        self.badge_row.setSpacing(6)
        self.badge_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.logo = QLabel()
        self.logo.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        self.logo.setVisible(False)
        self.title = QLabel("")
        self.title.setObjectName("HeroTitle")
        self.title.setWordWrap(True)
        self.sub = QLabel("")
        self.sub.setObjectName("HeroSub")
        self.availability = QLabel("")
        self.availability.setObjectName("HeroSub")
        self.availability.setWordWrap(True)
        self.availability.setMaximumWidth(620)
        text.addLayout(self.badge_row)
        text.addWidget(self.logo)
        text.addWidget(self.title)
        text.addWidget(self.sub)
        text.addWidget(self.availability)
        row.addLayout(text, 1)
        self.primary = QPushButton("")
        self.primary.setObjectName("Primary")
        self.primary.setMinimumWidth(190)
        row.addWidget(self.primary, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(row)

    def set_title(self, title: str, subtitle: str) -> None:
        self._title = title
        self.title.setText(title)
        self.sub.setText(subtitle)
        self._render_art()

    def set_badges(self, badges) -> None:
        clear_layout(self.badge_row)
        for text, kind in badges:
            self.badge_row.addWidget(badge(text, kind))

    def set_art(self, cover: QPixmap | None, logo: QPixmap | None) -> None:
        self._cover = cover if cover is not None and not cover.isNull() else None
        self._logo = logo if logo is not None and not logo.isNull() else None
        self._render_art()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.cover.setGeometry(self.rect())
        self.overlay.setGeometry(self.rect())
        self._render_art()

    def _fit_height(self) -> None:
        """Make room for the text block so nothing is drawn over the logo or the title."""
        needed = self.overlay.sizeHint().height()
        self.setMinimumHeight(max(HERO_HEIGHT, needed))

    def _render_art(self) -> None:
        if self.width() < 10:
            return
        if self._cover is not None:
            self.cover.setStyleSheet("")
            self.cover.setText("")
            self.cover.setPixmap(rounded(self._cover, self.size(), HERO_RADIUS))
        else:
            self.cover.setPixmap(QPixmap())
            self.cover.setText(initials(self._title))
            self.cover.setStyleSheet("color: #3a4358; font-family: 'Space Grotesk'; "
                                     "font-size: 72px; font-weight: 700;")
        if self._logo is not None:
            self.logo.setPixmap(self._logo.scaled(self.LOGO_MAX, Qt.AspectRatioMode.KeepAspectRatio,
                                                  Qt.TransformationMode.SmoothTransformation))
            self.logo.setVisible(True)
            self.title.setVisible(False)
        else:
            self.logo.setVisible(False)
            self.title.setVisible(True)
        self._fit_height()


class ProjectPage(QWidget):
    back_requested = Signal()

    def __init__(self, services, images, actions, parent=None) -> None:
        super().__init__(parent)
        self._services = services
        self._images = images
        self._actions = actions
        self._project: CatalogProject | None = None
        self._availability: Availability | None = None
        self._request_id = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 14, 20, 0)
        outer.setSpacing(8)
        top = QHBoxLayout()
        back = QPushButton(icon("back", "#e9edf5", 16), t("project.back"))
        back.setObjectName("Ghost")
        back.clicked.connect(self.back_requested.emit)
        top.addWidget(back)
        top.addStretch(1)
        outer.addLayout(top)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        body_host = QWidget()
        body = QVBoxLayout(body_host)
        body.setContentsMargins(12, 4, 24, 28)
        body.setSpacing(18)
        self.scroll.setWidget(body_host)
        outer.addWidget(self.scroll, 1)

        self.hero = HeroFrame()
        self.hero.primary.clicked.connect(self._on_primary)
        body.addWidget(self.hero)

        columns = QHBoxLayout()
        columns.setSpacing(18)
        columns.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.left = QVBoxLayout()
        self.right = QVBoxLayout()
        for layout in (self.left, self.right):
            layout.setSpacing(16)
            layout.setContentsMargins(0, 0, 0, 0)
        left_host, right_host = QWidget(), QWidget()
        left_host.setLayout(self.left)
        right_host.setLayout(self.right)
        columns.addWidget(left_host, 3)
        columns.addWidget(right_host, 2)
        body.addLayout(columns)
        body.addStretch(1)

    # ----- loading -----

    def load(self, project: CatalogProject) -> None:
        self._project = project
        self._availability = None
        self._request_id += 1
        self._fill_hero(project)
        self._fill_columns(project)
        self.scroll.verticalScrollBar().setValue(0)
        fade_in(self.scroll.widget())
        if self._services.library.get(project.id) is not None:
            self._set_primary_installed()
            return
        self._set_primary_checking()
        request = self._request_id
        run_async(self._services.resolver.resolve, project,
                  on_ok=lambda a: self._on_resolved(request, a),
                  on_err=lambda e: self._on_resolve_failed(request, e), parent=self)

    def _fill_hero(self, project: CatalogProject) -> None:
        self.hero.set_title(project.game_title, project.project_name)
        status_kind = {"available": "success", "development": "warning"}.get(project.status, "default")
        badges = [(t(status_label_key(project.status)), status_kind)]
        badges += [(kind.capitalize(), "accent") for kind in project.project_types]
        if project.made_with_ai:
            badges.append((t("badge.made_with_ai"), "warning"))
        if project.requires_original_assets == "yes":
            badges.append((t("badge.original_files"), "warning"))
        self.hero.set_badges(badges)
        self._apply_art(project)

    def _fill_columns(self, project: CatalogProject) -> None:
        clear_layout(self.left)
        clear_layout(self.right)
        about = project.long_description or project.description or t("detail.no_description")
        self.left.addWidget(_panel(t("project.about"), _wrap(about)))

        sources = list(dict.fromkeys(project.sources))[:8]
        if sources:
            self.left.addWidget(_panel(t("project.sources"),
                                       _link_list([(u, u) for u in sources], strip_scheme=True)))
        self.left.addStretch(1)

        if project.custom:
            self.right.addWidget(_panel(t("custom.section"), self._custom_buttons(project.id)))
        self.right.addWidget(_panel(t("project.info"), _info_rows(project)))
        links = [(t("detail.official_page"), project.official_url),
                 (t("detail.repository"), project.repository_url),
                 (t("detail.releases_page"), project.releases_url),
                 (t("detail.documentation"), project.documentation_url),
                 (t("detail.discord"), project.discord_url)]
        links = [(label, url) for label, url in links if url]
        if links:
            self.right.addWidget(_panel(t("project.links"), _link_list(links)))
        related = [(link.label, link.url) for link in project.related_links]
        if related:
            self.right.addWidget(_panel(t("project.related"), _link_list(related)))
        self.right.addStretch(1)

    # ----- primary action state -----

    def _set_primary_checking(self) -> None:
        self.hero.primary.setText(t("availability.checking"))
        self.hero.primary.setObjectName("Primary")
        self.hero.primary.setEnabled(False)
        self.hero.availability.setText(t("detail.checking"))
        self._restyle(self.hero.primary)

    def _set_primary_installed(self) -> None:
        record = self._services.library.get(self._project.id)
        version = record.installed_version or t("library.version_unknown")
        self.hero.primary.setText(t("availability.play"))
        self.hero.primary.setObjectName("Play")
        self.hero.primary.setEnabled(True)
        self.hero.availability.setText(t("library.version", version=version))
        self._restyle(self.hero.primary)

    def _restyle(self, widget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _on_resolved(self, request: int, availability: Availability) -> None:
        if request != self._request_id or self._project is None:
            return
        self._availability = availability
        primary = self.hero.primary
        if availability.action is PrimaryAction.MANUAL:
            self.hero.availability.setText(self._reason(availability))
            primary.setText(t("custom.register"))
            primary.setObjectName("Primary")
            primary.setEnabled(True)
        elif availability.action is PrimaryAction.INSTALL:
            build = availability.build
            self.hero.availability.setText(
                f"{t('detail.release_build')}: {build.asset.name}   ·   "
                f"{t('detail.release_tag')}: {build.release.tag or '—'}")
            primary.setText(t("availability.install"))
            primary.setObjectName("Primary")
            primary.setEnabled(True)
        elif availability.action is PrimaryAction.OPEN_PAGE:
            self.hero.availability.setText(self._reason(availability))
            primary.setText(t("availability.open_page"))
            primary.setObjectName("Primary")
            primary.setEnabled(True)
        else:
            self.hero.availability.setText(self._reason(availability) or t("availability.unavailable"))
            primary.setText(t("availability.unavailable"))
            primary.setObjectName("Primary")
            primary.setEnabled(False)
        self._restyle(primary)

    def _on_resolve_failed(self, request: int, exc: Exception) -> None:
        if request != self._request_id:
            return
        self.hero.availability.setText(t("error.unexpected", reason=exc.__class__.__name__))
        self.hero.primary.setText(t("availability.unavailable"))
        self.hero.primary.setEnabled(False)

    def _reason(self, availability: Availability) -> str:
        if not availability.reason_key:
            return ""
        return t(availability.reason_key, **availability.reason_arguments)

    def _apply_art(self, project: CatalogProject) -> None:
        if self._images is None:
            return
        cover = self._images.pixmap(project.cover_url) if project.cover_url else None
        logo = self._images.pixmap(project.logo_url) if project.logo_url else None
        self.hero.set_art(cover, logo)

    def _custom_buttons(self, project_id: str) -> QWidget:
        host = QWidget()
        host.setObjectName("Transparent")
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        edit = QPushButton(t("custom.edit"))
        edit.clicked.connect(lambda: self._actions.edit_custom_app(project_id))
        remove = QPushButton(t("custom.remove"))
        remove.setObjectName("Danger")
        remove.clicked.connect(lambda: self._actions.remove_custom_app(project_id))
        row.addWidget(edit)
        row.addWidget(remove)
        row.addStretch(1)
        return host

    def refresh_art(self) -> None:
        """Re-read artwork after the image settings changed (loading, memory limit)."""
        if self._project is not None:
            self._apply_art(self._project)

    def refresh_cover(self, url: str) -> None:
        if self._project is None or url not in (self._project.cover_url, self._project.logo_url):
            return
        self._apply_art(self._project)

    def refresh_state(self) -> None:
        """Called by the main window when installs or the library change."""
        if self._project is None:
            return
        if self._services.library.get(self._project.id) is not None:
            self._set_primary_installed()
        elif self._actions.is_installing(self._project.id):
            self.hero.primary.setText(t("install.downloading"))
            self.hero.primary.setEnabled(False)
            self._restyle(self.hero.primary)

    def _on_primary(self) -> None:
        if self._project is None:
            return
        if self._services.library.get(self._project.id) is not None:
            self._actions.play(self._project.id)
            return
        if self._availability is None:
            return
        if self._availability.action is PrimaryAction.MANUAL:
            self._actions.register_manual(self._project)
            return
        if self._availability.action is PrimaryAction.OPEN_PAGE:
            QDesktopServices.openUrl(QUrl(self._availability.page_url))
            return
        if self._availability.action is PrimaryAction.INSTALL:
            original = (t("detail.original_files_yes") if self._project.requires_original_assets == "yes"
                        else t("detail.original_files_no"))
            answer = QMessageBox.question(
                self, t("install.confirm_title", name=self._project.project_name),
                t("install.confirm_body", source=self._availability.build.repository, original_note=original),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._actions.start_install(self._project, self._availability)
                self.refresh_state()


# ----- panel builders -----

def _panel(title: str, content: QWidget) -> QFrame:
    frame = QFrame()
    frame.setObjectName("Panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 16, 20, 18)
    layout.setSpacing(12)
    heading = QLabel(title)
    heading.setObjectName("SectionTitle")
    layout.addWidget(heading)
    layout.addWidget(content)
    return frame


def _wrap(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _link_list(items, strip_scheme: bool = False) -> QWidget:
    host = QWidget()
    host.setObjectName("Transparent")
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    for label, url in items:
        shown = url.replace("https://", "", 1) if strip_scheme else label
        button = QPushButton(icon("external", "#8db4ff", 14), shown)
        button.setObjectName("LinkRow")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip(url)
        button.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
        layout.addWidget(button)
    return host


def _info_rows(project: CatalogProject) -> QWidget:
    rows = [
        (t("project.authors"), ", ".join(project.authors) or "—"),
        (t("project.platforms"), ", ".join(project.platforms) or "—"),
        (t("project.last_updated"), project.last_updated or "—"),
        (t("project.progress"), f"{project.progress}%" if project.progress is not None else "—"),
        (t("project.original_files"), {
            "yes": t("project.original_files_required"),
            "no": t("project.original_files_not_required"),
        }.get(project.requires_original_assets, t("project.original_files_unknown"))),
    ]
    host = QWidget()
    host.setObjectName("Transparent")
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    for key, value in rows:
        label = QLabel(key.upper())
        label.setObjectName("InfoLabel")
        layout.addWidget(label)
        layout.addWidget(_wrap(value))
        layout.addSpacing(8)
    return host
