"""Settings: folders, catalog appearance, motion, performance, updates, diagnostics and about.

Each change is saved and applied immediately through the main window; nothing needs a restart.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..app.version import APP_NAME, __version__
from ..localization.i18n import t
from ..storage.settings import (CARD_SIZES, CONCURRENT_CHOICES, DISK_CACHE_CHOICES, GRID_ART,
                                IMAGE_CACHE_CHOICES, MOTION_LEVELS)
from .format import human_size
from .icons import icon


def _panel() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 16, 20, 18)
    layout.setSpacing(12)
    return frame, layout


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setWordWrap(True)
    return label


class SettingsPage(QWidget):
    def __init__(self, services, actions, parent=None) -> None:
        super().__init__(parent)
        self._services = services
        self._actions = actions

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        root = QVBoxLayout(host)
        root.setContentsMargins(28, 24, 28, 18)
        root.setSpacing(16)
        scroll.setWidget(host)
        outer.addWidget(scroll)

        title = QLabel(t("settings.title"))
        title.setObjectName("PageTitle")
        root.addWidget(title)

        root.addWidget(self._folders_panel())
        root.addWidget(self._appearance_panel())
        root.addWidget(self._motion_panel())
        root.addWidget(self._performance_panel())
        root.addWidget(self._updates_panel())
        root.addWidget(self._catalog_panel())
        root.addWidget(self._about_panel())
        root.addStretch(1)
        self.set_catalog_status(None)
        self.refresh_cache_usage()

    # ----- panels -----

    def _folders_panel(self) -> QFrame:
        panel, layout = _panel()
        layout.addWidget(_heading(t("settings.section_folders")))
        self.library_edit = QLineEdit(self._services.settings.settings.library_dir)
        self.download_edit = QLineEdit(self._services.settings.settings.download_dir)
        layout.addWidget(self._labelled(t("settings.library_dir"), self.library_edit, self._pick_library))
        layout.addWidget(self._labelled(t("settings.download_dir"), self.download_edit, self._pick_download))
        layout.addWidget(_hint(t("settings.locked_downloads")))
        return panel

    def _appearance_panel(self) -> QFrame:
        panel, layout = _panel()
        layout.addWidget(_heading(t("settings.section_appearance")))
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        form.addRow(t("settings.grid_art"), self._combo(
            "grid_art", [(t(f"settings.grid_art_{v}"), v) for v in GRID_ART]))
        form.addRow(t("settings.card_size"), self._combo(
            "card_size", [(t(f"settings.card_size_{v}"), v) for v in CARD_SIZES]))
        layout.addLayout(form)
        layout.addWidget(self._check("show_card_details", t("settings.show_details")))
        layout.addWidget(_hint(t("settings.appearance_hint")))
        return panel

    def _motion_panel(self) -> QFrame:
        panel, layout = _panel()
        layout.addWidget(_heading(t("settings.section_motion")))
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.addRow(t("settings.motion_level"), self._combo(
            "motion_level", [(t(f"settings.motion_{v}"), v) for v in MOTION_LEVELS]))
        layout.addLayout(form)
        layout.addWidget(_hint(t("settings.motion_hint")))
        return panel

    def _performance_panel(self) -> QFrame:
        panel, layout = _panel()
        layout.addWidget(_heading(t("settings.section_performance")))
        layout.addWidget(self._check("load_images", t("settings.load_images")))
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        form.addRow(t("settings.image_cache"), self._combo(
            "image_cache_size", [(str(n), n) for n in IMAGE_CACHE_CHOICES]))
        form.addRow(t("settings.disk_cache"), self._combo(
            "disk_cache_mb", [(f"{n} MB" if n < 1000 else f"{n // 1000} GB", n) for n in DISK_CACHE_CHOICES]))
        form.addRow(t("settings.concurrent_downloads"), self._combo(
            "max_concurrent_downloads", [(str(n), n) for n in CONCURRENT_CHOICES]))
        layout.addLayout(form)
        cache_row = QHBoxLayout()
        self.cache_label = QLabel("")
        self.cache_label.setObjectName("Muted")
        cache_row.addWidget(self.cache_label, 1)
        clear = QPushButton(icon("trash", "#e9edf5", 16), t("settings.clear_cache"))
        clear.clicked.connect(self._actions.clear_image_cache)
        cache_row.addWidget(clear)
        layout.addLayout(cache_row)
        layout.addWidget(self._check("refresh_catalog_on_start", t("settings.refresh_on_start")))
        layout.addWidget(self._check("check_updates_on_start", t("settings.check_updates_on_start")))
        layout.addWidget(_hint(t("settings.performance_hint")))
        return panel

    def _updates_panel(self) -> QFrame:
        panel, layout = _panel()
        layout.addWidget(_heading(t("settings.section_updates")))
        row = QHBoxLayout()
        self.launcher_update_label = QLabel(t("settings.launcher_update_idle", version=__version__))
        self.launcher_update_label.setObjectName("Muted")
        self.launcher_update_label.setWordWrap(True)
        row.addWidget(self.launcher_update_label, 1)
        check = QPushButton(icon("retry", "#e9edf5", 16), t("settings.check_launcher_update"))
        check.clicked.connect(self._actions.check_launcher_update)
        row.addWidget(check)
        layout.addLayout(row)
        layout.addWidget(_hint(t("settings.updates_hint")))
        layout.addWidget(self._check("notifications", t("settings.notifications")))
        return panel

    def _catalog_panel(self) -> QFrame:
        panel, layout = _panel()
        layout.addWidget(_heading(t("settings.section_catalog")))
        row = QHBoxLayout()
        self.catalog_label = QLabel("")
        self.catalog_label.setObjectName("Muted")
        row.addWidget(self.catalog_label, 1)
        refresh = QPushButton(icon("retry", "#e9edf5", 16), t("settings.refresh_catalog"))
        refresh.clicked.connect(self._actions.refresh_catalog)
        row.addWidget(refresh)
        layout.addLayout(row)
        return panel

    def _about_panel(self) -> QFrame:
        panel, layout = _panel()
        layout.addWidget(_heading(t("settings.section_about")))
        layout.addWidget(QLabel(f"{APP_NAME} · {t('settings.version', version=__version__)}"))
        row = QHBoxLayout()
        row.addWidget(_hint(t("settings.diagnostics_hint")), 1)
        export = QPushButton(icon("folder", "#e9edf5", 16), t("settings.export_diagnostics"))
        export.clicked.connect(self._actions.export_diagnostics)
        row.addWidget(export)
        layout.addLayout(row)
        layout.addWidget(_hint(t("settings.updates")))
        return panel

    # ----- controls -----

    def _labelled(self, label: str, edit: QLineEdit, pick) -> QWidget:
        holder = QWidget()
        holder.setObjectName("Transparent")
        col = QVBoxLayout(holder)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        caption = QLabel(label)
        caption.setObjectName("Muted")
        col.addWidget(caption)
        row = QHBoxLayout()
        edit.setReadOnly(True)
        row.addWidget(edit, 1)
        browse = QPushButton(t("settings.browse"))
        browse.clicked.connect(lambda: pick(edit))
        row.addWidget(browse)
        col.addLayout(row)
        return holder

    def _combo(self, key: str, options) -> QComboBox:
        box = QComboBox()
        box.setMinimumWidth(200)
        for label, value in options:
            box.addItem(label, value)
        current = getattr(self._services.settings.settings, key)
        box.setCurrentIndex(max(0, box.findData(current)))
        box.currentIndexChanged.connect(lambda _: self._changed(key, box.currentData()))
        return box

    def _check(self, key: str, label: str) -> QCheckBox:
        box = QCheckBox(label)
        box.setChecked(bool(getattr(self._services.settings.settings, key)))
        box.setCursor(Qt.CursorShape.PointingHandCursor)
        box.toggled.connect(lambda value: self._changed(key, value))
        return box

    def _changed(self, key: str, value) -> None:
        self._services.settings.update(**{key: value})
        self._actions.apply_settings()
        if key == "disk_cache_mb":
            self.refresh_cache_usage()

    def refresh_cache_usage(self) -> None:
        self.cache_label.setText(t("settings.cache_usage", size=human_size(self._actions.image_cache_usage())))

    def set_launcher_update_text(self, text: str) -> None:
        self.launcher_update_label.setText(text)

    # ----- folder pickers -----

    def _pick_library(self, edit: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, t("settings.library_dir"), edit.text())
        if folder:
            self._services.settings.set_library_dir(Path(folder))
            edit.setText(self._services.settings.settings.library_dir)
            self._actions.library_location_changed()

    def _pick_download(self, edit: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, t("settings.download_dir"), edit.text())
        if folder:
            self._services.settings.set_download_dir(Path(folder))
            edit.setText(self._services.settings.settings.download_dir)

    def set_catalog_status(self, snapshot) -> None:
        if snapshot is None:
            self.catalog_label.setText(t("settings.catalog_status_none"))
            return
        when = (datetime.fromtimestamp(snapshot.fetched_at).strftime("%Y-%m-%d %H:%M")
                if snapshot.fetched_at else "?")
        self.catalog_label.setText(t("settings.catalog_status", when=when, source=snapshot.source))
