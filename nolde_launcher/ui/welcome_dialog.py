"""First-launch welcome: the launcher is in Early Access, and new versions will keep arriving."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ..app.version import APP_NAME, REPO_URL, VERSION_LABEL
from ..localization.i18n import t
from .icons import icon


class WelcomeDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("welcome.title"))
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setObjectName("WelcomeDialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(14)

        badge = QLabel(VERSION_LABEL.upper())
        badge.setObjectName("BadgeAccent")
        badge.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)

        title = QLabel(t("welcome.heading", name=APP_NAME))
        title.setObjectName("PageTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        for key in ("welcome.body_early", "welcome.body_updates", "welcome.body_feedback"):
            paragraph = QLabel(t(key))
            paragraph.setObjectName("Muted")
            paragraph.setWordWrap(True)
            layout.addWidget(paragraph)

        row = QHBoxLayout()
        row.setSpacing(10)
        repo = QPushButton(icon("code", "#e9edf5", 16), t("welcome.repository"))
        repo.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REPO_URL)))
        row.addWidget(repo)
        row.addStretch(1)
        ok = QPushButton(t("welcome.ok"))
        ok.setObjectName("Primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        layout.addLayout(row)
