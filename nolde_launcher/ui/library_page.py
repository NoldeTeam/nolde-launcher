"""Library: installed games with Play, sorting, playtime, updates, folder access and removal."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, QUrl, Qt, Signal
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu,
                               QPushButton, QToolButton, QVBoxLayout, QWidget)

from ..localization.i18n import t
from .dialogs import ThemedMessage as QMessageBox
from ..services.install_manager import InstallError, resolve_inside
from .card_grid import CardGrid
from .format import duration, time_ago
from .icons import icon
from .widgets import GameCard, card_width

SORTS = ("recent", "name", "installed", "playtime")


class LibraryPage(QWidget):
    update_requested = Signal(str)  # project id: the user chose "Update" in the card menu
    add_requested = Signal()        # "Add my own app"
    explore_requested = Signal()    # go to Discover

    def __init__(self, services, actions, project_lookup, parent=None) -> None:
        super().__init__(parent)
        self._services = services
        self._actions = actions
        self._project_lookup = project_lookup   # callable(project_id) -> CatalogProject | None
        self._updates: dict[str, str] = {}      # project id -> newer version available
        self.images = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 18)
        root.setSpacing(14)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel(t("library.title"))
        title.setObjectName("PageTitle")
        titles.addWidget(title)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        titles.addWidget(self.count_label)
        header.addLayout(titles, 1)

        self.add_btn = QPushButton(t("custom.add_button"))
        self.add_btn.clicked.connect(self.add_requested.emit)
        header.addWidget(self.add_btn)
        self.check_btn = QPushButton(icon("retry", "#e9edf5", 16), t("library.check_updates"))
        self.check_btn.clicked.connect(self._actions.check_updates)
        header.addWidget(self.check_btn)

        sort_label = QLabel(t("library.sort"))
        sort_label.setObjectName("Muted")
        header.addWidget(sort_label)
        self.sort_box = QComboBox()
        self.sort_box.setMinimumWidth(170)
        for key in SORTS:
            self.sort_box.addItem(t(f"library.sort_{key}"), key)
        self.sort_box.currentIndexChanged.connect(lambda _: self.refresh())
        header.addWidget(self.sort_box)
        root.addLayout(header)

        self.grid = CardGrid(t("library.empty"), card_width(self._display().card_size), show_empty=False)
        root.addWidget(self.grid, 1)  # the grid's own empty label is not used: the panel below replaces it

        # Shown when the library has nothing in it: two ways to fill it.
        self.empty_panel = QFrame()
        self.empty_panel.setObjectName("Panel")
        empty = QVBoxLayout(self.empty_panel)
        empty.setContentsMargins(40, 36, 40, 36)
        empty.setSpacing(18)
        message = QLabel(t("library.empty_message"))
        message.setObjectName("SectionTitle")
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel(t("library.empty_hint"))
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        add = QPushButton(t("custom.add_button"))
        add.setObjectName("Primary")
        add.clicked.connect(self.add_requested.emit)
        explore = QPushButton(t("library.explore"))
        explore.clicked.connect(self.explore_requested.emit)
        buttons.addWidget(add)
        buttons.addWidget(explore)
        buttons.addStretch(1)
        empty.addStretch(1)
        empty.addWidget(message)
        empty.addWidget(hint)
        empty.addLayout(buttons)
        empty.addStretch(1)
        self.empty_panel.hide()
        root.addWidget(self.empty_panel, 1)

    def _display(self):
        return self._services.settings.settings

    def set_updates(self, updates: dict[str, str]) -> None:
        self._updates = dict(updates)
        self.refresh()

    def _ordered(self):
        records = self._services.library.records()
        key = self.sort_box.currentData()
        if key == "recent":
            records.sort(key=lambda r: r.last_played_at or "", reverse=True)
        elif key == "installed":
            records.sort(key=lambda r: r.installed_at or "", reverse=True)
        elif key == "playtime":
            records.sort(key=lambda r: r.play_seconds, reverse=True)
        return records

    def refresh(self) -> None:
        records = self._ordered()
        self._records = {r.project_id: r for r in records}
        self.count_label.setText(t("library.count", count=len(records)))
        self.grid.set_entries([r.project_id for r in records], self._make_card,
                              t("library.empty"))
        self.empty_panel.setVisible(not records)
        self.grid.for_each(lambda pid, card: self._update_card(card, self._records[pid]))

    def rebuild(self) -> None:
        self.grid.set_card_width(card_width(self._display().card_size))
        self.grid.refresh_all()

    def refresh_covers(self) -> None:
        self.grid.for_each(lambda pid, card: self._apply_art(card, pid))

    def _apply_art(self, card: GameCard, project_id: str) -> None:
        if self.images is None:
            return
        project = self._project_lookup(project_id)
        if project is None:
            return
        mode = self._display().grid_art
        cover = self.images.pixmap(project.cover_url) if project.cover_url else None
        logo = self.images.pixmap(project.logo_url) if project.logo_url else None
        card.set_art(cover, logo, mode)

    def _make_card(self, project_id: str) -> GameCard:
        record = self._services.library.get(project_id)
        menu_btn = QToolButton()
        menu_btn.setObjectName("MenuButton")
        menu_btn.setIcon(icon("more", "#8a93a6", 18))
        menu_btn.setIconSize(QSize(18, 18))
        menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(menu_btn)
        for key, icon_name, handler in (
            ("library.open_folder", "folder", self._open_folder),
            ("library.verify", "shield", self._verify),
            ("library.choose_exe", "gamepad", self.choose_executable),
        ):
            action = QAction(icon(icon_name, "#e9edf5", 16), t(key), menu)
            action.triggered.connect(lambda _=False, r=record, h=handler: h(r))
            menu.addAction(action)
        update = QAction(icon("retry", "#8db4ff", 16), t("library.update"), menu)
        update.triggered.connect(lambda _=False, pid=project_id: self.update_requested.emit(pid))
        menu.addAction(update)
        menu.addSeparator()
        remove = QAction(icon("trash", "#e5534b", 16), t("library.uninstall"), menu)
        remove.triggered.connect(lambda _=False, r=record: self._uninstall(r))
        menu.addAction(remove)
        menu_btn.setMenu(menu)

        display = self._display()
        card = GameCard(project_id, record.game_title, "", overlay="play",
                        overlay_tooltip=t("library.play"), menu=menu_btn,
                        width=card_width(display.card_size), details=display.show_card_details)
        card.overlay_clicked.connect(self._actions.play)
        card.activated.connect(self._actions.open_project)
        self._update_card(card, record)  # a freshly built card needs its text and badges too
        return card

    def _update_card(self, card: GameCard, record) -> None:
        version = record.installed_version or t("library.version_unknown")
        played = (t("library.last_played", when=time_ago(record.last_played_at))
                  if record.last_played_at else t("library.never_played"))
        parts = [t("library.installed_version", version=version), played]
        if record.play_seconds:
            parts.append(t("library.playtime", time=duration(record.play_seconds)))
        card.title.setText(record.game_title)
        card.set_subtitle(" · ".join(parts))
        badges = []
        if self._services.launcher.is_running(record.project_id):
            badges.append((t("library.running_badge"), "success"))
        elif record.state == "needs_setup" or not record.main_executable:
            badges.append((t("library.needs_setup"), "warning"))
        else:
            badges.append((t("availability.installed"), "accent"))
        if record.project_id in self._updates:
            badges.append((t("library.update_badge", version=self._updates[record.project_id]), "warning"))
        card.replace_badges(badges)
        self._apply_art(card, record.project_id)

    def _install_dir(self, record) -> Path:
        return self._services.library.install_dir(record)

    def _open_folder(self, record) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._install_dir(record))))

    def _verify(self, record) -> None:
        self._actions.verify_install(record)

    def choose_executable(self, record) -> None:
        install_dir = self._install_dir(record).resolve()
        path, _ = QFileDialog.getOpenFileName(self, t("library.choose_exe"), str(install_dir),
                                              "Executables (*.exe);;All files (*)")
        if not path:
            return
        try:
            relative = Path(path).resolve().relative_to(install_dir).as_posix()
            resolve_inside(install_dir, relative)
        except (InstallError, ValueError):
            QMessageBox.warning(self, t("common.error"),
                                t("error.unexpected", reason="the file is outside the game folder"))
            return
        self._services.library.set_main_executable(record.project_id, relative)
        self.refresh()

    def _uninstall(self, record) -> None:
        answer = QMessageBox.question(
            self, t("library.uninstall_title", name=record.project_name),
            t("library.uninstall_body"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._services.library.uninstall(record.project_id)
        except (OSError, InstallError) as exc:
            QMessageBox.warning(self, t("common.error"), t("error.unexpected", reason=str(exc)))
        self.refresh()
        self._actions.library_changed()
