"""Nolde Launcher entry point.

Run from source:  python main.py
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from nolde_launcher.app.context import build_services
from nolde_launcher.app.version import APP_NAME
from nolde_launcher.localization.i18n import set_locale
from nolde_launcher.storage.paths import logs_dir
from nolde_launcher.ui.fonts import load_fonts
from nolde_launcher.ui.loading_screen import LoadingScreen, StartupResult
from nolde_launcher.ui.main_window import MainWindow
from nolde_launcher.ui.theme import APP_ICON_PATH, STYLESHEET
from nolde_launcher.ui.workers import wait_for_workers


def _setup_logging() -> None:
    # Operational events only: versions, catalog/download/install outcomes. No tokens,
    # no user file contents, and no Windows user name in messages.
    logging.basicConfig(
        filename=logs_dir() / "launcher.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )


def main() -> int:
    _setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    load_fonts()  # must run after QApplication exists and before styling
    app.setFont(QFont("Inter", 10))
    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    set_locale("en")

    services = build_services()
    loading = LoadingScreen(services)
    window: dict[str, MainWindow] = {}

    def open_main(result: StartupResult) -> None:
        main_window = MainWindow(services, result.snapshot, result.error)
        window["main"] = main_window
        main_window.show()
        loading.close()

    loading.startup_complete.connect(open_main)
    loading.show()
    loading.start()
    code = app.exec()
    wait_for_workers()  # let background threads finish before Qt tears down
    return code


if __name__ == "__main__":
    sys.exit(main())
