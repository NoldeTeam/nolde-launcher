"""Downloads: active, paused and finished transfers with real progress, speed and time left."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
                               QWidget)

from ..localization.i18n import t
from ..services.download_manager import DownloadStatus, DownloadTask
from . import motion
from .format import duration, human_size
from .widgets import CoverLabel, badge

ACTIVE = (DownloadStatus.QUEUED, DownloadStatus.RUNNING, DownloadStatus.PAUSED)
BAR_SCALE = 1000


class DownloadCard(QFrame):
    cancel_requested = Signal(int)
    pause_requested = Signal(int)
    resume_requested = Signal(int)
    retry_requested = Signal(str)
    remove_requested = Signal(int)

    def __init__(self, task: DownloadTask, title: str, cover_url: str, images, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        self.task_id = task.task_id
        self.project_id = task.project_id
        self._bar_anim: QPropertyAnimation | None = None
        self._state = "active"
        self.section_is_active: bool | None = None  # which list the card currently sits in

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 16, 12)
        row.setSpacing(16)

        self.thumb = CoverLabel(title, QSize(104, 58), self)
        if images is not None:
            self.thumb.set_pixmap(images.pixmap(cover_url))
        row.addWidget(self.thumb)

        body = QVBoxLayout()
        body.setSpacing(6)
        top = QHBoxLayout()
        self.title = QLabel(title)
        self.title.setObjectName("SectionTitle")
        top.addWidget(self.title, 1)
        self.status = badge("", "default")
        top.addWidget(self.status)
        body.addLayout(top)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.setRange(0, BAR_SCALE)
        body.addWidget(self.bar)

        self.detail = QLabel("")
        self.detail.setObjectName("Muted")
        self.detail.setWordWrap(True)
        body.addWidget(self.detail)
        row.addLayout(body, 1)

        actions = QVBoxLayout()
        actions.setSpacing(6)
        self.secondary = QPushButton("")
        self.secondary.setFixedWidth(118)
        self.secondary.clicked.connect(self._on_secondary)
        actions.addWidget(self.secondary)
        self.primary = QPushButton("")
        self.primary.setFixedWidth(118)
        self.primary.clicked.connect(self._on_primary)
        actions.addWidget(self.primary)
        actions.addStretch(1)
        row.addLayout(actions)
        self.update_from(task, title)

    def _on_primary(self) -> None:
        if self._state in ("active", "paused"):
            self.cancel_requested.emit(self.task_id)
        elif self._state == "failed":
            self.retry_requested.emit(self.project_id)
        else:
            self.remove_requested.emit(self.task_id)

    def _on_secondary(self) -> None:
        if self._state == "active":
            self.pause_requested.emit(self.task_id)
        elif self._state == "paused":
            self.resume_requested.emit(self.task_id)

    def update_from(self, task: DownloadTask, title: str) -> None:
        self.title.setText(title)
        paused = task.status is DownloadStatus.PAUSED
        if task.status is DownloadStatus.RUNNING or task.status is DownloadStatus.QUEUED:
            self._state = "active"
            self.status.setText(t("downloads.status_running" if task.status is DownloadStatus.RUNNING
                                  else "downloads.status_queued"))
            self._set_badge_kind("accent")
        elif paused:
            self._state = "paused"
            self.status.setText(t("downloads.status_paused"))
            self._set_badge_kind("warning")
        elif task.status is DownloadStatus.COMPLETED:
            self._state = "done"
            self.status.setText(t("downloads.status_completed"))
            self._set_badge_kind("success")
        elif task.status is DownloadStatus.FAILED:
            self._state = "failed"
            self.status.setText(t("downloads.status_failed"))
            self._set_badge_kind("danger")
        else:
            self._state = "done"
            self.status.setText(t("downloads.status_cancelled"))
            self._set_badge_kind("default")

        # Buttons per state
        self.secondary.setVisible(self._state in ("active", "paused"))
        self.secondary.setText(t("downloads.resume") if paused else t("downloads.pause"))
        self.primary.setText({"active": t("downloads.cancel"), "paused": t("downloads.cancel"),
                              "failed": t("downloads.retry"), "done": t("downloads.remove")}[self._state])
        for widget in (self.primary, self.secondary, self.bar, self.status):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.bar.setObjectName("Done" if task.status is DownloadStatus.COMPLETED
                               else "Failed" if task.status is DownloadStatus.FAILED
                               else "Paused" if paused else "")

        if task.total_bytes:
            self.bar.setRange(0, BAR_SCALE)
            target = int(BAR_SCALE * min(task.bytes_done, task.total_bytes) / task.total_bytes)
            if task.status is DownloadStatus.COMPLETED:
                target = BAR_SCALE
            self._animate_bar(target)
        elif task.is_active and not paused:
            self.bar.setRange(0, 0)  # busy indicator while the size is unknown
        else:
            self.bar.setRange(0, BAR_SCALE)
            self._animate_bar(BAR_SCALE if task.status is DownloadStatus.COMPLETED else self.bar.value())
        self.detail.setText(self._detail_text(task))
        self.detail.setStyleSheet("color: #e5534b;" if task.status is DownloadStatus.FAILED else "")

    def _set_badge_kind(self, kind: str) -> None:
        self.status.setObjectName({"success": "BadgeSuccess", "accent": "BadgeAccent",
                                   "warning": "BadgeWarning", "danger": "BadgeDanger"}.get(kind, "Badge"))
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def _animate_bar(self, target: int) -> None:
        if self.bar.minimum() == 0 and self.bar.maximum() == 0:
            self.bar.setRange(0, BAR_SCALE)
        if not motion.animations_enabled():
            self.bar.setValue(target)
            return
        # Reused, not DeleteWhenStopped: see GameCard._animate_lift.
        if self._bar_anim is None:
            self._bar_anim = QPropertyAnimation(self.bar, b"value", self)
            self._bar_anim.setDuration(260)
            self._bar_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._bar_anim.stop()
        self._bar_anim.setStartValue(self.bar.value())
        self._bar_anim.setEndValue(target)
        self._bar_anim.start()

    def _detail_text(self, task: DownloadTask) -> str:
        parts = []
        if task.total_bytes:
            parts.append(t("downloads.progress", done=human_size(task.bytes_done),
                           total=human_size(task.total_bytes)))
        else:
            parts.append(t("downloads.progress_unknown", done=human_size(task.bytes_done)))
        if task.status is DownloadStatus.RUNNING and task.speed_bps:
            parts.append(t("downloads.speed", speed=human_size(task.speed_bps)))
            if task.total_bytes and task.speed_bps > 0:
                parts.append(t("downloads.eta", time=duration((task.total_bytes - task.bytes_done) / task.speed_bps)))
        if task.status is DownloadStatus.PAUSED:
            parts.append(t("downloads.paused_hint"))
        if task.error:
            parts.append(task.error)
        return "  ·  ".join(parts)


class DownloadsPage(QWidget):
    retry_requested = Signal(str)

    def __init__(self, manager, title_for, cover_for, images, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._title_for = title_for      # callable(project_id) -> str
        self._cover_for = cover_for      # callable(project_id) -> str (cover URL)
        self._images = images
        self._cards: dict[int, DownloadCard] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 18)
        root.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel(t("nav.downloads"))
        title.setObjectName("PageTitle")
        titles.addWidget(title)
        self.summary = QLabel("")
        self.summary.setObjectName("Muted")
        titles.addWidget(self.summary)
        header.addLayout(titles, 1)
        self.clear_btn = QPushButton(t("downloads.clear_finished"))
        self.clear_btn.clicked.connect(self._clear_finished)
        header.addWidget(self.clear_btn)
        root.addLayout(header)

        self.active_title = self._section(t("downloads.section_active"))
        root.addWidget(self.active_title)
        self.active_box = QVBoxLayout()
        self.active_box.setSpacing(10)
        root.addLayout(self.active_box)
        self.finished_title = self._section(t("downloads.section_finished"))
        root.addWidget(self.finished_title)
        self.finished_box = QVBoxLayout()
        self.finished_box.setSpacing(10)
        root.addLayout(self.finished_box)

        self.empty = QLabel(t("downloads.empty"))
        self.empty.setObjectName("Empty")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty)
        root.addStretch(1)

        self._manager.task_changed.connect(self.on_task_changed)
        for task in self._manager.tasks():
            self.on_task_changed(task)

    def refresh_covers(self) -> None:
        if self._images is None:
            return
        for task_id, card in self._cards.items():
            task = self._manager.task(task_id)
            if task is not None:
                card.thumb.set_pixmap(self._images.pixmap(self._cover_for(task.project_id)))

    def _section(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionTitle")
        return label

    def on_task_changed(self, task: DownloadTask) -> None:
        card = self._cards.get(task.task_id)
        if card is None:
            card = DownloadCard(task, self._title_for(task.project_id),
                                self._cover_for(task.project_id), self._images, self)
            card.cancel_requested.connect(self._manager.cancel)
            card.pause_requested.connect(self._manager.pause)
            card.resume_requested.connect(self._manager.resume)
            card.retry_requested.connect(self.retry_requested.emit)
            card.remove_requested.connect(self._remove)
            self._cards[task.task_id] = card
        card.update_from(task, self._title_for(task.project_id))
        self._place(card, task)
        self._refresh_summary()

    def _place(self, card: DownloadCard, task: DownloadTask) -> None:
        want_active = task.status in ACTIVE
        if card.section_is_active is want_active:
            return
        if card.section_is_active is not None:
            (self.active_box if card.section_is_active else self.finished_box).removeWidget(card)
        if want_active:
            self.active_box.insertWidget(0, card)  # newest first
        else:
            self.finished_box.addWidget(card)
        card.section_is_active = want_active
        card.show()

    def _remove(self, task_id: int) -> None:
        self._manager.remove(task_id)
        card = self._cards.pop(task_id, None)
        if card is not None:
            self.active_box.removeWidget(card)
            self.finished_box.removeWidget(card)
            card.deleteLater()
        self._refresh_summary()

    def _clear_finished(self) -> None:
        self._manager.clear_finished()
        for task_id in list(self._cards):
            task = self._manager.task(task_id)
            if task is None:
                self._remove(task_id)
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        active = self.active_box.count()
        finished = self.finished_box.count()
        self.summary.setText(t("downloads.summary", active=active, finished=finished))
        self.active_title.setVisible(active > 0)
        self.finished_title.setVisible(finished > 0)
        self.empty.setVisible(active == 0 and finished == 0)
        self.clear_btn.setEnabled(finished > 0)
