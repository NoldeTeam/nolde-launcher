"""Form for adding or editing an app the user manages. Validation is the same as the service's."""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout)

from ..localization.i18n import t
from .dialogs import ThemedMessage as QMessageBox
from ..services.custom_apps import CustomAppError, CustomAppSpec, validate
from .dialogs import ThemedDialog


class CustomAppDialog(ThemedDialog):
    def __init__(self, spec: CustomAppSpec | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("custom.dialog_title_edit" if spec and spec.id else "custom.dialog_title_add"))
        self.setMinimumWidth(560)
        self._spec = spec or CustomAppSpec(name="", management="manual", asset_filter="*Windows*.zip")

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        self.name = QLineEdit(self._spec.name)
        self.author = QLineEdit(self._spec.author)
        self.display = QLineEdit(self._spec.display_name)
        self.display.setPlaceholderText(t("custom.display_placeholder"))
        self.management = QComboBox()
        self.management.addItem(t("custom.mode_managed"), "managed")
        self.management.addItem(t("custom.mode_manual"), "manual")
        self.management.setCurrentIndex(max(0, self.management.findData(self._spec.management)))
        self.repo = QLineEdit(self._spec.repository_url)
        self.repo.setPlaceholderText("https://github.com/owner/repo")
        self.asset = QLineEdit(self._spec.asset_filter)
        self.folder = QLineEdit(self._spec.folder_name)
        self.folder.setPlaceholderText(t("custom.folder_placeholder"))
        self.tags = QLineEdit(", ".join(self._spec.tags))
        self.tags.setPlaceholderText(t("custom.tags_placeholder"))
        self.icon = QLineEdit(self._spec.icon_url)
        self.icon.setPlaceholderText("https://…/icon.png")
        self.files = QPlainTextEdit("\n".join(self._spec.files_to_add))
        self.files.setPlaceholderText(t("custom.files_placeholder"))
        self.files.setMaximumHeight(70)
        browse = QPushButton(t("custom.browse_files"))
        browse.clicked.connect(self._browse_files)
        self.mods_path = QLineEdit(self._spec.mods_path)
        self.mods_path.setPlaceholderText("mods")
        self.mod_sources = QPlainTextEdit("\n".join(self._spec.mod_sources))
        self.mod_sources.setPlaceholderText("https://github.com/owner/mod")
        self.mod_sources.setMaximumHeight(70)
        self.own_folder = QCheckBox(t("custom.own_folder"))
        self.own_folder.setChecked(self._spec.mods_own_folder)

        form.addRow(t("custom.name"), self.name)
        form.addRow(t("custom.author"), self.author)
        form.addRow(t("custom.display_name"), self.display)
        form.addRow(t("custom.management"), self.management)
        form.addRow(t("custom.repository"), self.repo)
        form.addRow(t("custom.asset_filter"), self.asset)
        form.addRow(t("custom.folder"), self.folder)
        form.addRow(t("custom.tags"), self.tags)
        form.addRow(t("custom.icon"), self.icon)
        files_box = QVBoxLayout()
        files_box.addWidget(self.files)
        files_box.addWidget(browse, 0)
        form.addRow(t("custom.files"), files_box)
        form.addRow(t("custom.mods_path"), self.mods_path)
        form.addRow(t("custom.mod_sources"), self.mod_sources)
        form.addRow("", self.own_folder)

        self.hint = QLabel(t("custom.form_hint"))
        self.hint.setObjectName("Muted")
        self.hint.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(t("common.cancel"))
        cancel.clicked.connect(self.reject)
        save = QPushButton(t("custom.save"))
        save.setObjectName("Primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)

        layout = self.body_layout
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)
        layout.addLayout(form)
        layout.addWidget(self.hint)
        layout.addLayout(buttons)
        self.result_spec: CustomAppSpec | None = None

    def _browse_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, t("custom.files"))
        if paths:
            current = [p for p in self.files.toPlainText().splitlines() if p.strip()]
            self.files.setPlainText("\n".join(current + paths))

    def _lines(self, widget: QPlainTextEdit) -> list[str]:
        return [line.strip() for line in widget.toPlainText().splitlines() if line.strip()]

    def _save(self) -> None:
        spec = CustomAppSpec(
            name=self.name.text(), id=self._spec.id, author=self.author.text(),
            display_name=self.display.text(),
            management=self.management.currentData(),
            repository_url=self.repo.text(), asset_filter=self.asset.text(),
            folder_name=self.folder.text(),
            tags=[t_.strip() for t_ in self.tags.text().split(",") if t_.strip()],
            icon_url=self.icon.text(),
            files_to_add=self._lines(self.files),
            mods_path=self.mods_path.text(),
            mod_sources=self._lines(self.mod_sources),
            mods_own_folder=self.own_folder.isChecked(),
        )
        try:
            self.result_spec = validate(spec)
        except CustomAppError as exc:
            QMessageBox.warning(self, t("common.error"), str(exc))
            return
        self.accept()
