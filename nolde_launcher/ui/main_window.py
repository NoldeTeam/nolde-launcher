"""Main window: sidebar, Continue card, navigation and the content stack.

The project page is a stack page inside this window, not a separate dialog, so
Back returns to wherever the user was.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QPropertyAnimation, QRect, QSize, QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QInputDialog, QLabel, QMainWindow,
                               QMessageBox, QPushButton, QStackedWidget, QToolButton, QVBoxLayout, QWidget)

import requests
from PySide6.QtCore import qVersion
from PySide6.QtWidgets import QFileDialog

from ..app.version import APP_NAME, NOLDE_WEBSITE, REPO_URL, VERSION_LABEL, __version__
from ..services.diagnostics import build_report
from ..services.update_service import (check_game_updates, check_latest_release,
                                      download_installer, installer_arguments, is_installed_build)
from ..storage.paths import logs_dir
from ..services.integrity import build_manifest, load_manifest, save_manifest
from ..services.integrity import verify_install as check_install
from .notifier import Notifier
from ..localization.i18n import t
from ..services.catalog_service import CatalogSnapshot
from ..services.launch_manager import LaunchError, LaunchRequest
from ..services.library_service import LibraryService, make_library_store
from ..services.source_resolver import Availability
from ..storage.paths import cache_dir, user_data_dir
from .discover_page import DiscoverPage
from .downloads_page import DownloadsPage
from .icons import icon
from .image_cache import ImageCache
from .install_controller import InstallController
from .library_page import LibraryPage
from .project_page import ProjectPage
from .settings_page import SettingsPage
from .theme import LOGO_PATH
from . import motion
from .titlebar import TitleBar, layout_grips, make_grips
from .widgets import ContinueCard, Toast, fade_in, slide_in
from .format import time_ago
from .workers import run_async

log = logging.getLogger("nolde.ui")
STARTUP_TASKS_SWITCH = "NOLDE_SKIP_STARTUP_TASKS"  # set by the test suite

PAGE_LIBRARY, PAGE_DISCOVER, PAGE_DOWNLOADS, PAGE_SETTINGS, PAGE_PROJECT = range(5)
NAV = (
    (PAGE_LIBRARY, "nav.library", "library"),
    (PAGE_DISCOVER, "nav.discover", "discover"),
    (PAGE_DOWNLOADS, "nav.downloads", "downloads"),
    (PAGE_SETTINGS, "nav.settings", "settings"),
)
RUNNING_POLL_MS = 2500


class MainWindow(QMainWindow):
    def __init__(self, services, startup_snapshot: CatalogSnapshot | None,
                 startup_error: str = "") -> None:
        super().__init__()
        self.services = services
        self.setWindowTitle(APP_NAME)
        # Frameless: the title bar is drawn in the app colour. Edge grips keep resizing working.
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.resize(1240, 800)
        self.setMinimumSize(920, 600)
        self._projects_by_id: dict[str, object] = {}
        self._snapshot = startup_snapshot
        self._catalog_busy = False
        self._return_page = PAGE_LIBRARY
        self._nav_buttons: dict[int, QPushButton] = {}
        self._indicator_anim: QPropertyAnimation | None = None
        self._filter_buttons: dict[bool, QPushButton] = {}

        self.images = ImageCache(cache_dir(), self)
        self.images.ready.connect(self._on_image_ready)
        self.installs = InstallController(services, self._choose_executable_from_list, self)
        self.installs.status_changed.connect(lambda _pid, msg: self.statusBar().showMessage(msg))
        self.installs.finished_ok.connect(self._on_install_ok)
        self.installs.finished_error.connect(self._on_install_error)
        self.installs.library_changed.connect(self._refresh_library)
        self.installs.downloads.task_changed.connect(lambda _task: self._update_downloads_badge())

        self._run_timer = QTimer(self)
        self._run_timer.setInterval(RUNNING_POLL_MS)
        self._run_timer.timeout.connect(self._poll_running)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.titlebar = TitleBar(self)
        self.titlebar.title.setText(f"{APP_NAME}  ·  {VERSION_LABEL}")
        root.addWidget(self.titlebar)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        root.addLayout(row, 1)
        row.addWidget(self._build_sidebar())
        self._grips = make_grips(self)

        self.stack = QStackedWidget()
        self.library_page = LibraryPage(services, self, self._project_for)
        self.library_page.images = self.images
        self.library_page.update_requested.connect(self.update_game)
        self._updates: dict[str, str] = {}
        self._setup_shortcuts()
        self.discover = DiscoverPage(services)
        self.discover.images = self.images
        self.discover.open_project.connect(self.open_project)
        self.discover.refresh_requested.connect(self.refresh_catalog)
        self.downloads_page = DownloadsPage(self.installs.downloads, self._title_for,
                                            self._cover_for, self.images)
        self.downloads_page.retry_requested.connect(self.retry_install)
        self.settings_page = SettingsPage(services, self)
        self.project_page = ProjectPage(services, self.images, self)
        self.project_page.back_requested.connect(self.go_back)
        for page in (self.library_page, self.discover, self.downloads_page,
                     self.settings_page, self.project_page):
            self.stack.addWidget(page)
        row.addWidget(self.stack, 1)

        self.toast = Toast(central)
        self.notifier = Notifier(icon("gamepad", "#e9edf5", 32), self,
                                 lambda: self.services.settings.settings.notifications, self)
        self.stack.currentChanged.connect(self._on_page_changed)
        self.discover.set_snapshot(startup_snapshot, startup_error)
        self.settings_page.set_catalog_status(startup_snapshot)
        self._index_projects()
        self._refresh_library()
        self._update_downloads_badge()
        self.apply_settings()
        self.show_page(PAGE_DISCOVER, animate=False)  # the catalog opens first
        if not os.environ.get(STARTUP_TASKS_SWITCH):  # tests run without popups or network checks
            if self.services.settings.settings.check_updates_on_start:
                QTimer.singleShot(2500, lambda: self.check_updates(silent=True))
            if self.services.settings.settings.check_launcher_updates:
                QTimer.singleShot(4000, lambda: self.check_launcher_update(silent=True))
            if not self.services.settings.settings.welcome_seen:
                QTimer.singleShot(900, self._show_welcome)

    def apply_settings(self) -> None:
        """Push every appearance and performance setting into the running app. No restart needed."""
        s = self.services.settings.settings
        motion.configure(s.motion_level)
        self.notifier.set_enabled(s.notifications)
        self.images.set_enabled(s.load_images)
        self.images.set_limit(s.image_cache_size)
        self.images.set_disk_limit(s.disk_cache_mb)
        self.installs.downloads.set_max_concurrent(s.max_concurrent_downloads)
        self.discover.rebuild()
        self.library_page.rebuild()
        self.project_page.refresh_art()
        self._move_indicator(animate=False)

    # ----- layout -----

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        self.sidebar = sidebar
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(272)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 0, 14)
        side.setSpacing(0)

        logo = QLabel()
        logo.setObjectName("Logo")
        pix = QPixmap(str(LOGO_PATH))
        if not pix.isNull():
            logo.setPixmap(pix.scaledToWidth(236, Qt.TransformationMode.SmoothTransformation))
        side.addWidget(logo)

        self.continue_card = ContinueCard()
        self.continue_card.play_requested.connect(self.play)
        wrap = QVBoxLayout()
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.addWidget(self.continue_card)
        side.addLayout(wrap)
        side.addSpacing(14)

        for index, key, icon_name in NAV:
            button = QPushButton(icon(icon_name, "#8793a8", 18), t(key))
            button.setObjectName("NavButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIconSize(QSize(18, 18))
            button.clicked.connect(lambda _=False, i=index: self._nav_clicked(i))
            side.addWidget(button)
            self._nav_buttons[index] = button

        filters_label = QLabel(t("sidebar.filters"))
        filters_label.setObjectName("SidebarSection")
        side.addWidget(filters_label)
        for installed_only, key in ((False, "filter.all_projects"), (True, "filter.installed")):
            button = QPushButton(t(key))
            button.setObjectName("FilterButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, v=installed_only: self._set_filter(v))
            side.addWidget(button)
            self._filter_buttons[installed_only] = button

        side.addStretch(1)
        # Icon-only link to the Nolde website, in the corner where the version used to be.
        site_row = QHBoxLayout()
        site_row.setContentsMargins(18, 0, 0, 0)
        site = QToolButton()
        site.setObjectName("SiteButton")
        site.setIcon(icon("globe", "#8793a8", 18))
        site.setIconSize(QSize(18, 18))
        site.setToolTip(t("nav.website"))
        site.setCursor(Qt.CursorShape.PointingHandCursor)
        site.setFixedSize(38, 38)
        site.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(NOLDE_WEBSITE)))
        site_row.addWidget(site)
        repo = QToolButton()
        repo.setObjectName("RepoButton")
        repo.setIcon(icon("code", "#8793a8", 18))
        repo.setIconSize(QSize(18, 18))
        repo.setToolTip(t("nav.repository"))
        repo.setCursor(Qt.CursorShape.PointingHandCursor)
        repo.setFixedSize(38, 38)
        repo.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REPO_URL)))
        site_row.addSpacing(6)
        site_row.addWidget(repo)
        site_row.addStretch(1)
        side.addLayout(site_row)
        self._nav_indicator = QFrame(sidebar)
        self._nav_indicator.setObjectName("NavIndicator")
        self._nav_indicator.setStyleSheet("#NavIndicator { background: #2f6fed; border-radius: 1px; }")
        self._indicator_anim = QPropertyAnimation(self._nav_indicator, b"geometry", self)
        self._indicator_anim.setDuration(260)
        self._indicator_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        return sidebar

    def _set_active(self, button: QPushButton, active: bool) -> None:
        button.setProperty("active", "true" if active else "false")
        button.style().unpolish(button)
        button.style().polish(button)

    def _nav_clicked(self, index: int) -> None:
        self.show_page(index)

    def _set_filter(self, installed_only: bool) -> None:
        self.discover.installed_only = installed_only
        self.discover._apply()
        for value, button in self._filter_buttons.items():
            self._set_active(button, value == installed_only)
        self.show_page(PAGE_DISCOVER)

    def show_page(self, index: int, animate: bool = True) -> None:
        previous = self.stack.currentIndex()
        if previous != index:
            self.stack.setCurrentIndex(index)
            if animate:
                direction = 1 if index > previous else -1
                page = self.stack.currentWidget()
                slide_in(page, dx=direction * 36)
                fade_in(page)
        for nav_index, button in self._nav_buttons.items():
            self._set_active(button, nav_index == index)
        for value, button in self._filter_buttons.items():
            self._set_active(button, self.discover.installed_only == value and index == PAGE_DISCOVER)
        self._move_indicator(animate=animate)

    def _move_indicator(self, animate: bool = True) -> None:
        """Slide the accent bar to the nav item of the current page (or of the page the project came from)."""
        index = self.stack.currentIndex()
        if index == PAGE_PROJECT:
            index = self._return_page
        button = self._nav_buttons.get(index)
        if button is None or not hasattr(self, "_nav_indicator"):
            return
        origin = button.mapTo(self.sidebar, QPoint(0, 0))
        target = QRect(10, origin.y() + 9, 3, max(button.height() - 18, 4))
        anim = self._indicator_anim
        anim.stop()
        if animate and motion.animations_enabled() and self._nav_indicator.isVisible():
            anim.setStartValue(self._nav_indicator.geometry())
            anim.setEndValue(target)
            anim.start()
        else:
            self._nav_indicator.setGeometry(target)

    def _on_page_changed(self, index: int) -> None:
        for nav_index, button in self._nav_buttons.items():
            self._set_active(button, nav_index == index or (index == PAGE_PROJECT and nav_index == self._return_page))

    # ----- catalog -----

    def _index_projects(self) -> None:
        self._projects_by_id = {p.id: p for p in (self._snapshot.projects if self._snapshot else ())}

    def _project_for(self, project_id: str):
        return self._projects_by_id.get(project_id)

    def _title_for(self, project_id: str) -> str:
        project = self._projects_by_id.get(project_id)
        if project is not None:
            return project.project_name
        record = self.services.library.get(project_id)
        return record.project_name if record else project_id

    def _cover_for(self, project_id: str) -> str:
        project = self._projects_by_id.get(project_id)
        return (project.cover_url or project.logo_url) if project else ""

    def refresh_catalog(self) -> None:
        if self._catalog_busy:
            return
        self._catalog_busy = True
        self.statusBar().showMessage(t("loading.checking_catalog"))
        run_async(self.services.catalog.refresh, on_ok=self._on_refresh_ok,
                  on_err=self._on_refresh_err, parent=self)

    def _on_refresh_ok(self, snapshot: CatalogSnapshot) -> None:
        self._catalog_busy = False
        self._snapshot = snapshot
        self._index_projects()
        self.discover.set_snapshot(snapshot)
        self.settings_page.set_catalog_status(snapshot)
        self.statusBar().showMessage(t("loading.ready"), 4000)
        self.toast.show_message(t("loading.ready"), "success", 3000)

    def _on_refresh_err(self, exc: Exception) -> None:
        self._catalog_busy = False
        reason = str(exc)
        log.warning("catalog refresh failed: %s", exc.__class__.__name__)
        self.discover.set_snapshot(self._snapshot, reason)
        self.toast.show_message(t("discover.load_failed", reason=reason), "error", 6000)

    def _on_image_ready(self, url: str) -> None:
        self.discover.refresh_card_covers()
        self.library_page.refresh_covers()
        self.downloads_page.refresh_covers()
        self.project_page.refresh_cover(url)

    # ----- project page -----

    def open_project(self, project_id: str) -> None:
        project = self._projects_by_id.get(project_id)
        if project is None:
            return
        if self.stack.currentIndex() != PAGE_PROJECT:
            self._return_page = self.stack.currentIndex()
        self.project_page.load(project)
        self.show_page(PAGE_PROJECT)

    def go_back(self) -> None:
        self.show_page(self._return_page if self._return_page != PAGE_PROJECT else PAGE_DISCOVER)

    def start_install(self, project, availability: Availability) -> None:
        if availability.build is None:
            return
        self.installs.start(project, availability.build)
        self.toast.show_message(t("install.downloading"), "info", 3000)
        self.project_page.refresh_state()
        self._update_downloads_badge()

    def retry_install(self, project_id: str) -> None:
        if self.installs.retry(project_id):
            self.toast.show_message(t("install.downloading"), "info", 3000)
        else:
            self.toast.show_message(t("error.unexpected", reason="retry unavailable"), "error")

    def is_installing(self, project_id: str) -> bool:
        return self.installs.is_busy(project_id)

    # ----- library and play -----

    def library_changed(self) -> None:
        self._refresh_library()

    def _refresh_library(self) -> None:
        self.library_page.refresh()
        self._update_continue()
        if self.project_page._project is not None:
            self.project_page.refresh_state()

    def _update_continue(self) -> None:
        records = self.services.library.records()
        if not records:
            self.continue_card.clear()
            return
        played = [r for r in records if r.last_played_at]
        pick = max(played, key=lambda r: r.last_played_at) if played else records[0]
        subtitle = (t("continue.last_played", when=time_ago(pick.last_played_at))
                    if pick.last_played_at else t("continue.ready"))
        self.continue_card.set_game(pick.project_id, pick.game_title, subtitle)

    def _update_downloads_badge(self) -> None:
        active = sum(1 for task in self.installs.downloads.tasks() if task.is_active)
        label = t("nav.downloads") + (f"   {active}" if active else "")
        self._nav_buttons[PAGE_DOWNLOADS].setText(label)

    def play(self, project_id: str) -> None:
        svc = self.services
        record = svc.library.get(project_id)
        if record is None:
            self.toast.show_message(t("error.unexpected", reason="not installed"), "error")
            return
        if svc.launcher.is_running(project_id):
            self.toast.show_message(t("library.running"), "info", 3000)
            return
        if not record.main_executable:
            self.library_page.choose_executable(record)
            record = svc.library.get(project_id)
            if record is None or not record.main_executable:
                return
        if not record.first_run_confirmed:
            answer = QMessageBox.question(
                self, t("library.first_run_title", name=record.project_name),
                t("library.first_run_body"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            svc.library.confirm_first_run(project_id)
        request = LaunchRequest(project_id, record.install_folder, record.main_executable,
                                tuple(record.launch_args))
        try:
            svc.launcher.launch(svc.library.library_dir, request)
        except LaunchError as exc:
            self.toast.show_message(t("library.launch_error", reason=str(exc)), "error", 7000)
            self._refresh_library()
            return
        svc.library.mark_played(project_id)
        self.toast.show_message(t("library.started", name=record.project_name), "success", 3500)
        self._refresh_library()
        if not self._run_timer.isActive():
            self._run_timer.start()

    # ----- keyboard -----

    def _setup_shortcuts(self) -> None:
        bindings = [
            ("Ctrl+F", self._focus_search),
            ("Esc", self._escape),
            ("F5", self.refresh_catalog),
            ("Ctrl+1", lambda: self.show_page(PAGE_LIBRARY)),
            ("Ctrl+2", lambda: self.show_page(PAGE_DISCOVER)),
            ("Ctrl+3", lambda: self.show_page(PAGE_DOWNLOADS)),
            ("Ctrl+4", lambda: self.show_page(PAGE_SETTINGS)),
        ]
        self._shortcuts = []
        for keys, handler in bindings:
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.activated.connect(handler)
            self._shortcuts.append(shortcut)

    def _focus_search(self) -> None:
        self.show_page(PAGE_DISCOVER)
        self.discover.search.setFocus()
        self.discover.search.selectAll()

    def _escape(self) -> None:
        if self.stack.currentIndex() == PAGE_PROJECT:
            self.go_back()

    # ----- game updates -----

    def check_updates(self, silent: bool = False) -> None:
        records = self.services.library.records()
        if not records:
            if not silent:
                self.toast.show_message(t("library.no_updates"), "info", 3000)
            return
        run_async(check_game_updates, records, self._project_for, self.services.resolver,
                  on_ok=lambda found: self._on_updates(found, silent),
                  on_err=lambda exc: self._on_updates({}, silent), parent=self)

    def _on_updates(self, found: dict[str, str], silent: bool) -> None:
        if found:
            self.notifier.notify(t("notify.updates_title"),
                                 t("notify.updates_body", count=len(found)))
        self._updates = found
        self.library_page.set_updates(found)
        if found:
            self.toast.show_message(t("library.updates_found", count=len(found)), "info", 6000)
        elif not silent:
            self.toast.show_message(t("library.no_updates"), "success", 3000)

    def update_game(self, project_id: str) -> None:
        project = self._project_for(project_id)
        if project is None:
            self.toast.show_message(t("library.no_catalog_entry"), "error", 5000)
            return
        run_async(self.services.resolver.resolve, project,
                  on_ok=lambda availability: self._confirm_update(project, availability),
                  on_err=lambda exc: self.toast.show_message(
                      t("error.unexpected", reason=exc.__class__.__name__), "error"),
                  parent=self)

    def _confirm_update(self, project, availability: Availability) -> None:
        if availability.build is None:
            self.toast.show_message(t("library.update_unavailable"), "error", 6000)
            return
        answer = QMessageBox.question(
            self, t("library.update_title", name=project.project_name),
            t("library.update_body", version=availability.build.release.tag or "—"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.installs.update(project, availability.build)
            self.toast.show_message(t("install.downloading"), "info", 3000)

    # ----- launcher update (verified download; installing stays manual) -----

    def _show_welcome(self) -> None:
        """Shown once, on the first launch. Marked as seen when it is closed."""
        from .welcome_dialog import WelcomeDialog
        dialog = WelcomeDialog(self)
        dialog.exec()
        self.services.settings.update(welcome_seen=True)

    def check_launcher_update(self, silent: bool = False) -> None:
        """Look for a newer launcher on GitHub. `silent` is used at startup: nothing is shown
        unless an update is ready, and errors are kept out of the way."""
        if not silent:
            self.settings_page.set_launcher_update_text(t("settings.launcher_checking"))
        run_async(self._launcher_update_job,
                  on_ok=lambda result: self._on_launcher_update(result, silent),
                  on_err=lambda exc: self._on_launcher_update_error(exc, silent), parent=self)

    def _launcher_update_job(self):
        release = check_latest_release(requests.get)
        if release is None:
            return ("current", None, None)
        installer = download_installer(release, self.services.settings.download_dir / "launcher")
        return ("ready", release, installer)

    def _on_launcher_update(self, result, silent: bool) -> None:
        state, release, installer = result
        if state == "current":
            if not silent:
                self.settings_page.set_launcher_update_text(
                    t("settings.launcher_current", version=__version__))
            return
        text = t("settings.launcher_ready", version=release.version, path=str(installer.parent))
        self.settings_page.set_launcher_update_text(text)
        self.notifier.notify(t("notify.launcher_title"), text)
        if not is_installed_build():
            self.toast.show_message(t("settings.launcher_source_build", version=release.version), "info", 8000)
            return
        answer = QMessageBox.question(
            self, t("update.ready_title"),
            t("update.ready_body", version=release.version),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self._install_update(installer)
        else:
            self.settings_page.set_launcher_update_text(t("update.later", version=release.version))

    def _on_launcher_update_error(self, exc: Exception, silent: bool) -> None:
        if silent:
            log.info("launcher update check skipped: %s", exc.__class__.__name__)
            return
        self.settings_page.set_launcher_update_text(t("settings.launcher_update_failed", reason=str(exc)))

    def _install_update(self, installer: Path) -> None:
        """Start the verified installer in silent mode, then close this launcher so the upgrade
        can replace its files. The installer restarts the launcher when it finishes."""
        try:
            subprocess.Popen(installer_arguments(installer), shell=False, close_fds=True)
        except OSError as exc:
            self.toast.show_message(t("update.failed", reason=exc.__class__.__name__), "error", 8000)
            return
        QApplication.quit()

    def export_diagnostics(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, t("settings.export_diagnostics"),
                                              "nolde-diagnostics.txt", "Text (*.txt)")
        if not path:
            return
        report = build_report(self.services, logs_dir() / "launcher.log", qVersion())
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(report)
        self.toast.show_message(t("settings.diagnostics_saved"), "success", 5000)

    def clear_image_cache(self) -> None:
        self.images.clear_disk()
        self.settings_page.refresh_cache_usage()
        self.toast.show_message(t("settings.cache_cleared"), "success", 3000)

    def image_cache_usage(self) -> int:
        return self.images.disk_usage()

    def _poll_running(self) -> None:
        for project_id, seconds in self.services.launcher.pop_finished_playtime():
            self.services.library.add_playtime(project_id, seconds)
        running = self.services.launcher.running_ids()
        self.library_page.refresh()
        if not running:
            self._run_timer.stop()

    def library_location_changed(self) -> None:
        self.services.library = LibraryService(make_library_store(user_data_dir() / "library.json"),
                                               self.services.settings.library_dir)
        self._refresh_library()
        self.toast.show_message(t("settings.locked_downloads"), "info", 6000)

    # ----- install callbacks -----

    def _choose_executable_from_list(self, candidates: list[str]) -> str | None:
        item, ok = QInputDialog.getItem(self, t("install.choose_exe_title"),
                                        t("install.choose_exe_body"), candidates, 0, False)
        return item if ok else None

    def _on_install_ok(self, project_id: str, message: str) -> None:
        self._refresh_library()
        self.toast.show_message(message, "success", 6000)
        self._update_downloads_badge()
        self.notifier.notify(t("notify.install_done_title"), message)
        record = self.services.library.get(project_id)
        if record is not None:  # integrity record for the files as installed
            run_async(self._record_integrity_job, project_id,
                      self.services.library.install_dir(record), parent=self)

    # ----- integrity -----

    def _record_integrity_job(self, project_id: str, install_dir: Path) -> int:
        manifest = build_manifest(install_dir)
        save_manifest(project_id, manifest)
        return len(manifest["files"])

    def verify_install(self, record) -> None:
        install_dir = self.services.library.install_dir(record)
        manifest = load_manifest(record.project_id)
        if manifest is None:
            answer = QMessageBox.question(
                self, t("integrity.create_title"), t("integrity.create_body"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes:
                self.toast.show_message(t("integrity.building"), "info", 3000)
                run_async(self._record_integrity_job, record.project_id, install_dir,
                          on_ok=lambda count: self.toast.show_message(
                              t("integrity.recorded", name=record.project_name, count=count), "success", 5000),
                          on_err=lambda exc: self.toast.show_message(
                              t("error.unexpected", reason=exc.__class__.__name__), "error"),
                          parent=self)
            return
        self.toast.show_message(t("integrity.building"), "info", 2000)
        run_async(check_install, install_dir, manifest,
                  on_ok=lambda report: self._show_integrity(record, report),
                  on_err=lambda exc: self.toast.show_message(
                      t("error.unexpected", reason=exc.__class__.__name__), "error"),
                  parent=self)

    def _show_integrity(self, record, report) -> None:
        title = t("integrity.result_title", name=record.project_name)
        if report.ok and report.extra_count == 0:
            QMessageBox.information(self, title, t("integrity.ok", count=report.checked))
            return
        details = []
        for label, names in (("Missing", report.missing), ("Changed", report.changed)):
            details += [f"{label}: {name}" for name in names[:10]]
        text = t("integrity.problems", checked=report.checked, missing=report.missing_count,
                 changed=report.changed_count, extra=report.extra_count,
                 details="\n".join(details) or t("integrity.no_details"))
        if report.ok:
            QMessageBox.information(self, title, text)
        else:
            QMessageBox.warning(self, title, text)

    def _on_install_error(self, project_id: str, message: str) -> None:
        self.notifier.notify(t("notify.install_failed_title"), message)
        self.toast.show_message(message, "error", 8000)
        self.project_page.refresh_state()
        self._update_downloads_badge()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, lambda: self._move_indicator(animate=False))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._move_indicator(animate=False)
        self._place_grips()
        if self.toast.isVisible():
            self.toast._reposition()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self.titlebar.sync_state()
            self._place_grips()

    def _place_grips(self) -> None:
        visible = not (self.isMaximized() or self.isFullScreen())
        layout_grips(self._grips, self.width(), self.height(), visible)


