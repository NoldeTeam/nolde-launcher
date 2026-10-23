"""Startup screen: the logo and a progress bar. Nothing else.

Network work runs on a thread so the window never freezes.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from ..services.catalog_service import CatalogError, CatalogSnapshot
from .theme import LOGO_PATH

LOGO_WIDTH = 400
STEP_SETTINGS, STEP_REQUEST, STEP_CATALOG, STEP_DONE = 15, 40, 85, 100


@dataclass
class StartupResult:
    snapshot: CatalogSnapshot | None
    error: str = ""


class StartupWorker(QThread):
    progress = Signal(int)
    done = Signal(object)

    def __init__(self, services, parent=None) -> None:
        super().__init__(parent)
        self._services = services

    def run(self) -> None:
        self.progress.emit(STEP_SETTINGS)
        error = ""
        if not self._services.settings.settings.refresh_catalog_on_start:
            # Faster start: show the saved catalog, refresh later from the Discover page.
            snapshot = self._services.catalog.load_cached()
            if snapshot is not None:
                self.progress.emit(STEP_CATALOG)
                self.done.emit(StartupResult(snapshot, ""))
                return
        self.progress.emit(STEP_REQUEST)
        try:
            snapshot = self._services.catalog.refresh()
        except CatalogError as exc:
            error = str(exc)
            snapshot = self._services.catalog.load_cached()
        self.progress.emit(STEP_CATALOG)
        self.done.emit(StartupResult(snapshot, error))


class LoadingScreen(QWidget):
    startup_complete = Signal(object)

    def __init__(self, services, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(560, 360)
        self.setObjectName("LoadingRoot")
        self.setStyleSheet("#LoadingRoot { background: #0d1016; border: 1px solid #232a38; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 40, 60, 48)
        layout.setSpacing(36)
        layout.addStretch(1)

        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(LOGO_PATH))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaledToWidth(LOGO_WIDTH, Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(logo)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        layout.addWidget(self.bar)
        layout.addStretch(1)

        self._worker = StartupWorker(services, self)
        self._worker.progress.connect(self.bar.setValue)
        self._worker.done.connect(self._on_done)

    def start(self) -> None:
        self._worker.start()

    def _on_done(self, result: StartupResult) -> None:
        self.bar.setValue(STEP_DONE)
        self.startup_complete.emit(result)
