"""Themed dialogs: same frameless window and title bar as the launcher, instead of the system's.

ThemedDialog is the base for the launcher's own dialogs. ThemedMessage is a drop-in replacement
for QMessageBox.question/warning/information: the same calls and the same answers, drawn with
the launcher's title bar, so existing code only needs a different import.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

from ..localization.i18n import t
from .titlebar import TitleBar, layout_grips, make_grips


class ThemedDialog(QDialog):
    """Frameless dialog with the launcher's close button. Content goes into `body_layout`."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("ThemedDialog")
        self.setModal(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.titlebar = TitleBar(self, compact=True, on_close=self.reject)
        outer.addWidget(self.titlebar)
        self.body_layout = QVBoxLayout()
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self.body_layout, 1)
        self._grips = make_grips(self)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        layout_grips(self._grips, self.width(), self.height(), True)


class _MessageDialog(ThemedDialog):
    def __init__(self, parent, title: str, text: str, buttons: list[tuple[str, QMessageBox.StandardButton]]) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        self.choice = buttons[-1][1]  # what closing the dialog means: the last, negative choice
        body = QVBoxLayout()
        body.setContentsMargins(28, 20, 28, 24)
        body.setSpacing(18)
        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        heading.setWordWrap(True)
        message = QLabel(text)
        message.setObjectName("Muted")
        message.setWordWrap(True)
        message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.addWidget(heading)
        body.addWidget(message)
        row = QHBoxLayout()
        row.addStretch(1)
        for index, (label, value) in enumerate(buttons):
            button = QPushButton(label)
            button.setObjectName("Primary" if index == 0 else "")  # the first choice is the main one
            button.clicked.connect(lambda _=False, v=value: self._choose(v))
            row.addWidget(button)
        body.addLayout(row)
        self.body_layout.addLayout(body)

    def _choose(self, value) -> None:
        self.choice = value
        self.accept()


class ThemedMessage:
    """Same calls and answers as QMessageBox.question / warning / information."""

    StandardButton = QMessageBox.StandardButton

    @staticmethod
    def question(parent, title: str, text: str, *_, **__) -> QMessageBox.StandardButton:
        dialog = _MessageDialog(parent, title, text, [
            (t("common.yes"), QMessageBox.StandardButton.Yes),
            (t("common.no"), QMessageBox.StandardButton.No),
        ])
        dialog.exec()
        return dialog.choice

    @staticmethod
    def warning(parent, title: str, text: str, *_, **__) -> QMessageBox.StandardButton:
        dialog = _MessageDialog(parent, title, text, [(t("common.ok"), QMessageBox.StandardButton.Ok)])
        dialog.exec()
        return QMessageBox.StandardButton.Ok

    @staticmethod
    def information(parent, title: str, text: str, *_, **__) -> QMessageBox.StandardButton:
        return ThemedMessage.warning(parent, title, text)
