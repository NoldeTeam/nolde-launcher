"""Shared widgets: badges, tags, cover art, game cards, the Continue card and toasts."""

from __future__ import annotations

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRect, QRectF,
                            QSize, Qt, QTimer, Signal)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
                               QHBoxLayout, QLabel, QLayout, QPushButton, QSizePolicy, QToolButton,
                               QVBoxLayout, QWidget)

from . import icons, motion

COVER_W, COVER_H = 240, 135
RADIUS = 10
MAX_TAGS = 3
CARD_WIDTHS = {"small": 200, "medium": 240, "large": 300}


def card_width(name: str) -> int:
    return CARD_WIDTHS.get(name, COVER_W)


def badge(text: str, kind: str = "default") -> QLabel:
    label = QLabel(text)
    label.setObjectName({"success": "BadgeSuccess", "accent": "BadgeAccent",
                         "warning": "BadgeWarning", "danger": "BadgeDanger"}.get(kind, "Badge"))
    label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return label


def tag(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Tag")
    label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return label


def status_label_key(status: str) -> str:
    return {"available": "status.available", "development": "status.development",
            "archived": "status.archived"}.get(status, "status.unknown")


def rounded(pixmap: QPixmap, size: QSize, radius: int = RADIUS) -> QPixmap:
    """Scale to fill `size`, centre-crop, and clip to rounded corners."""
    scaled = pixmap.scaled(size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(size)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size.width(), size.height()), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(int((size.width() - scaled.width()) / 2),
                       int((size.height() - scaled.height()) / 2), scaled)
    painter.end()
    return out


def initials(title: str) -> str:
    words = [w for w in title.replace(":", " ").replace("-", " ").split() if w[:1].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or "?"


def clip(text: str, limit: int = 120) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


class FlowLayout(QLayout):
    """Places items left to right and wraps to a new line instead of squeezing them.
    Squeezing is what cut badge and tag text short ("Build po", "Sega Me")."""

    def __init__(self, parent=None, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        widest = max((item.sizeHint().width() for item in self._items), default=0)
        tallest = max((item.sizeHint().height() for item in self._items), default=0)
        m = self.contentsMargins()
        return QSize(widest + m.left() + m.right(), tallest + m.top() + m.bottom())

    def _layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = area.x(), area.y(), 0
        for item in self._items:
            size = item.sizeHint()
            if x > area.x() and x + size.width() > area.right() + 1:
                x = area.x()
                y += line_h + self._spacing
                line_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), size))
            x += size.width() + self._spacing
            line_h = max(line_h, size.height())
        return y + line_h - rect.y() + m.bottom()


def _row_host() -> tuple[QWidget, FlowLayout]:
    host = QWidget()
    host.setObjectName("Transparent")  # keep the card surface visible behind the row
    layout = FlowLayout(host)
    return host, layout


class CoverLabel(QLabel):
    """Cover art, or a placeholder with initials until the image arrives."""

    def __init__(self, title: str, size: QSize = QSize(COVER_W, COVER_H), parent=None) -> None:
        super().__init__(parent)
        self._title = title
        self._size = size
        self.setFixedSize(size)
        self.setObjectName("CoverPlaceholder")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(initials(title))

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        if pixmap is None or pixmap.isNull():
            self.setPixmap(QPixmap())
            self.setText(initials(self._title))
            return
        self.setText("")
        self.setPixmap(rounded(pixmap, self._size))


class CoverFrame(QFrame):
    """Cover container: artwork, an optional transparent logo centred on it, and the overlay action."""

    def __init__(self, title: str, size: QSize = QSize(COVER_W, COVER_H), parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("CoverFrame")
        self.setFixedSize(size)
        self.cover = CoverLabel(title, size, self)
        self.logo = QLabel(self)
        self.logo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo.hide()
        self._has_logo = False  # explicit state: isVisible() is false before the first show
        self.overlay: QPushButton | None = None

    def set_logo(self, pixmap: QPixmap | None) -> None:
        if pixmap is None or pixmap.isNull():
            self._has_logo = False
            self.logo.hide()
            return
        limit = QSize(self.width() - 36, self.height() - 34)
        scaled = pixmap.scaled(limit, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        self.logo.setPixmap(scaled)
        self.logo.resize(scaled.size())
        self._has_logo = True
        self.logo.show()
        self._place()

    def add_overlay(self, kind: str, tooltip: str) -> QPushButton:
        button = QPushButton(self)
        button.setObjectName("OverlayPlay" if kind == "play" else "OverlayInstall")
        button.setIcon(icons.icon("play_fill" if kind == "play" else "install_fill", "#ffffff", 18))
        button.setIconSize(QSize(18, 18))
        button.setFixedSize(40, 40)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip(tooltip)
        self.overlay = button
        self._place()
        return button

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.cover.setFixedSize(self.size())
        self._place()

    def _place(self) -> None:
        if self._has_logo:
            self.logo.move((self.width() - self.logo.width()) // 2,
                           (self.height() - self.logo.height()) // 2 - 4)
            self.logo.raise_()
        if self.overlay is not None:
            self.overlay.move(12, self.height() - self.overlay.height() - 12)
            self.overlay.raise_()


class GameCard(QFrame):
    """A game tile: cover with an overlay action, title, description, badges, tags and a menu."""

    activated = Signal(str)
    overlay_clicked = Signal(str)

    def __init__(self, project_id: str, title: str, subtitle: str, *, description: str = "",
                 overlay: str | None = None, overlay_tooltip: str = "",
                 badges: tuple[tuple[str, str], ...] = (), tags: tuple[str, ...] = (),
                 menu: QToolButton | None = None, width: int = COVER_W,
                 details: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.project_id = project_id
        self._details = details
        self.setObjectName("GameCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(width + 24)
        self._shadow: QGraphicsDropShadowEffect | None = None
        self._blur_anim: QPropertyAnimation | None = None
        self._offset_anim: QPropertyAnimation | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        cover_size = QSize(width, round(width * COVER_H / COVER_W))
        self.frame = CoverFrame(title, cover_size, parent=self)
        if overlay:
            button = self.frame.add_overlay(overlay, overlay_tooltip)
            button.clicked.connect(lambda: self.overlay_clicked.emit(self.project_id))
        layout.addWidget(self.frame)

        self.title = QLabel(title)
        self.title.setObjectName("GameCardTitle")
        self.title.setWordWrap(True)
        layout.addWidget(self.title)

        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("GameCardSub")
        self.subtitle.setWordWrap(True)
        self.subtitle.setVisible(bool(subtitle))
        layout.addWidget(self.subtitle)

        self.description = QLabel(clip(description))
        self.description.setObjectName("GameCardDesc")
        self.description.setWordWrap(True)
        self.description.setVisible(bool(description) and details)
        layout.addWidget(self.description)

        self._badge_host, self._badge_layout = _row_host()
        layout.addWidget(self._badge_host)
        self._tag_host, self._tag_layout = _row_host()
        layout.addWidget(self._tag_host)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 2, 0, 0)
        footer.addStretch(1)
        if menu is not None:
            footer.addWidget(menu)
        layout.addLayout(footer)

        self.replace_badges(badges)
        self.set_tags(tags)

    @property
    def cover(self) -> CoverLabel:
        return self.frame.cover

    def set_art(self, cover: QPixmap | None, logo: QPixmap | None, mode: str) -> None:
        """mode: cover_logo (both), cover (artwork only), logo (logo only), text (no artwork)."""
        show_cover = mode in ("cover_logo", "cover")
        show_logo = mode in ("cover_logo", "logo")
        self.cover.set_pixmap(cover if show_cover else None)
        self.frame.set_logo(logo if show_logo else None)

    def set_description(self, text: str) -> None:
        self.description.setText(clip(text))
        self.description.setVisible(self._details and bool(text))

    def set_details(self, details: bool) -> None:
        self._details = details
        self.description.setVisible(details and bool(self.description.text()))
        self._badge_host.setVisible(details and self._badge_layout.count() > 0)
        self._tag_host.setVisible(details and self._tag_layout.count() > 0)

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)
        self.subtitle.setVisible(bool(text))

    def replace_badges(self, badges) -> None:
        clear_layout(self._badge_layout)
        for text, kind in badges:
            self._badge_layout.addWidget(badge(text, kind))
        self._badge_host.setVisible(bool(badges) and self._details)

    def set_tags(self, tags) -> None:
        clear_layout(self._tag_layout)
        shown = list(tags)[:MAX_TAGS]
        for text in shown:
            self._tag_layout.addWidget(tag(text))
        self._tag_host.setVisible(bool(shown) and self._details)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.project_id)
        super().mousePressEvent(event)

    # Hover: the shadow lifts smoothly. Animations are created once and reused,
    # because Qt deletes an animation that uses DeleteWhenStopped once it finishes.
    def enterEvent(self, event) -> None:
        if motion.hover_enabled():
            self._animate_lift(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        # Always lower a lifted card, even while scrolling, so it never stays stuck up.
        if self._shadow is not None:
            self._animate_lift(False)
        super().leaveEvent(event)

    def _animate_lift(self, up: bool) -> None:
        if self._shadow is None:
            if not up:
                return
            self._shadow = QGraphicsDropShadowEffect(self)
            self._shadow.setColor(QColor(0, 0, 0, 170))
            self._shadow.setBlurRadius(0)
            self._shadow.setOffset(QPointF(0, 0))
            self.setGraphicsEffect(self._shadow)
            self._blur_anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
            self._blur_anim.setDuration(180)
            self._blur_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._offset_anim = QPropertyAnimation(self._shadow, b"offset", self)
            self._offset_anim.setDuration(180)
            self._offset_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._blur_anim.finished.connect(self._settle)
        if up:
            self._shadow.setEnabled(True)
        for anim in (self._blur_anim, self._offset_anim):
            anim.stop()
        self._blur_anim.setEndValue(26.0 if up else 0.0)
        self._offset_anim.setEndValue(QPointF(0, 8.0 if up else 0.0))
        self._blur_anim.start()
        self._offset_anim.start()

    def _settle(self) -> None:
        """Once a card is back down, switch its shadow off. A disabled effect is not drawn
        through an off-screen buffer, so idle cards cost nothing more. The effect object
        is kept (not deleted) because the animations still refer to it."""
        if self._shadow is not None and self._blur_anim.endValue() == 0.0:
            self._shadow.setEnabled(False)


class ContinueCard(QFrame):
    """The 'Continue' tile at the top of the sidebar: last played installed game."""

    play_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ContinueCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._project_id = ""
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 10, 10, 10)
        row.setSpacing(10)
        self.thumb = CoverLabel("?", QSize(52, 52), self)
        row.addWidget(self.thumb)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = QLabel("")
        self.title.setObjectName("ContinueTitle")
        self.title.setWordWrap(True)
        self.sub = QLabel("")
        self.sub.setObjectName("ContinueSub")
        self.sub.setWordWrap(True)
        text.addWidget(self.title)
        text.addWidget(self.sub)
        text.addStretch(1)
        row.addLayout(text, 1)
        self.play = QToolButton()
        self.play.setObjectName("MenuButton")
        self.play.setIcon(icons.icon("play_fill", "#2fa572", 22))
        self.play.setIconSize(QSize(22, 22))
        self.play.clicked.connect(lambda: self.play_requested.emit(self._project_id))
        row.addWidget(self.play, 0, Qt.AlignmentFlag.AlignVCenter)
        self.hide()

    def set_game(self, project_id: str, title: str, subtitle: str) -> None:
        self._project_id = project_id
        self.title.setText(title)
        self.sub.setText(subtitle)
        self.thumb.setText(initials(title))
        self.show()

    def clear(self) -> None:
        self._project_id = ""
        self.hide()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._project_id:
            self.play_requested.emit(self._project_id)
        super().mousePressEvent(event)


def fade_in(widget: QWidget, duration: int = 240, delay: int = 0, kind: str = "page") -> None:
    """Fade a widget in once, then release the effect so it costs nothing at rest.
    `delay` (ms) staggers several widgets. Safe if the widget is deleted meanwhile."""
    allowed = motion.card_motion_enabled() if kind == "card" else motion.animations_enabled()
    if not allowed:
        return
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def finish() -> None:
        try:
            if widget.graphicsEffect() is effect:
                widget.setGraphicsEffect(None)
        except RuntimeError:
            pass

    def start() -> None:
        try:
            anim.finished.connect(finish)
            anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        except RuntimeError:
            pass

    if delay > 0:
        QTimer.singleShot(delay, start)
    else:
        start()


_slides: dict[int, QPropertyAnimation] = {}


def slide_in(widget: QWidget, dx: int, duration: int = 280) -> None:
    """Glide a page in from `dx` pixels away while it fades in.
    Used by the stack so forward and back navigation move in opposite directions."""
    if not motion.animations_enabled():
        return
    target = widget.pos()
    widget.move(target.x() + dx, target.y())
    key = id(widget)
    previous = _slides.pop(key, None)
    if previous is not None:
        try:
            previous.stop()
        except RuntimeError:
            pass
    anim = QPropertyAnimation(widget, b"pos", widget)
    anim.setDuration(duration)
    anim.setStartValue(QPoint(target.x() + dx, target.y()))
    anim.setEndValue(target)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    _slides[key] = anim
    anim.finished.connect(lambda k=key: _slides.pop(k, None))
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


class Toast(QFrame):
    """Transient message in the bottom-right corner that slides and fades in."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 12, 16, 12)
        self.label = QLabel("")
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(360)
        row.addWidget(self.label)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._hide_animated)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(220)
        self._fade.finished.connect(self._on_fade_finished)  # connected once
        self.hide()

    def show_message(self, text: str, kind: str = "info", timeout_ms: int = 5000) -> None:
        accent = {"success": "#3aa578", "error": "#e5534b", "info": "#2f6fed"}.get(kind, "#2f6fed")
        self.setStyleSheet(f"#Panel {{ border-left: 3px solid {accent}; }}")
        self.label.setText(text)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.start()
        self._timer.start(timeout_ms)

    def _hide_animated(self) -> None:
        self._fade.stop()
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _on_fade_finished(self) -> None:
        if self._effect.opacity() < 0.5:
            self.hide()

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.move(parent.width() - self.width() - 24, parent.height() - self.height() - 40)
