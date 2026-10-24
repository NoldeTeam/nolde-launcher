"""Custom window chrome: a title bar in the app colour, window buttons, and edge grips.

The native frame is removed so the title bar can match the app. Moving and resizing
are handed to the operating system (startSystemMove / startSystemResize), so snapping,
Aero Shake and the native resize behaviour keep working.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from ..localization.i18n import t
from .icons import icon

BORDER = 6  # width of the invisible resize grips, in pixels


class WindowButton(QToolButton):
    def __init__(self, icon_name: str, tooltip: str, close: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self.setObjectName("WindowClose" if close else "WindowButton")
        self.setFixedSize(46, 38)
        self.setToolTip(tooltip)
        self.setIconSize(QSize(14, 14))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_icon()

    def set_icon_name(self, name: str) -> None:
        self._icon_name = name
        self._apply_icon()

    def _apply_icon(self) -> None:
        self.setIcon(icon(self._icon_name, "#8793a8", 14))


class TitleBar(QWidget):
    def __init__(self, window, parent=None, compact: bool = False, on_close=None) -> None:
        super().__init__(parent)
        self._window = window
        self.setObjectName("TitleBar")
        self.setFixedHeight(38)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 0, 0, 0)
        row.setSpacing(0)
        self.title = QLabel("")  # window buttons only; no title text in the bar
        self.title.setObjectName("TitleText")
        row.addWidget(self.title)
        row.addStretch(1)

        self.close_btn = WindowButton("x", t("titlebar.close"), close=True)
        self.close_btn.clicked.connect(on_close or window.close)
        if compact:  # dialogs: a close button only
            self.min_btn = self.max_btn = None
            row.addWidget(self.close_btn)
            return
        self.min_btn = WindowButton("minimize", t("titlebar.minimize"))
        self.max_btn = WindowButton("maximize", t("titlebar.maximize"))
        self.min_btn.clicked.connect(window.showMinimized)
        self.max_btn.clicked.connect(self.toggle_maximize)
        for button in (self.min_btn, self.max_btn, self.close_btn):
            row.addWidget(button)
        self.sync_state()

    def toggle_maximize(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()
        self.sync_state()

    def sync_state(self) -> None:
        if self.max_btn is not None:
            self.max_btn.set_icon_name("restore" if self._window.isMaximized() else "maximize")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximize()
        super().mouseDoubleClickEvent(event)


class ResizeGrip(QWidget):
    """Invisible strip on one edge or corner. Pressing it starts a system resize."""

    def __init__(self, window, edges, cursor, parent=None) -> None:
        super().__init__(parent)
        self._window = window
        self._edges = edges
        self.setCursor(cursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None:
                handle.startSystemResize(self._edges)
        event.accept()


def make_grips(window) -> list[ResizeGrip]:
    E = Qt.Edge
    C = Qt.CursorShape
    spec = [
        (E.LeftEdge, C.SizeHorCursor),
        (E.RightEdge, C.SizeHorCursor),
        (E.TopEdge, C.SizeVerCursor),
        (E.BottomEdge, C.SizeVerCursor),
        (E.LeftEdge | E.TopEdge, C.SizeFDiagCursor),
        (E.RightEdge | E.TopEdge, C.SizeBDiagCursor),
        (E.LeftEdge | E.BottomEdge, C.SizeBDiagCursor),
        (E.RightEdge | E.BottomEdge, C.SizeFDiagCursor),
    ]
    return [ResizeGrip(window, edges, cursor, window) for edges, cursor in spec]


def layout_grips(grips, width: int, height: int, visible: bool) -> None:
    m = BORDER
    rects = [
        (0, m, m, height - 2 * m),
        (width - m, m, m, height - 2 * m),
        (m, 0, width - 2 * m, m),
        (m, height - m, width - 2 * m, m),
        (0, 0, m, m),
        (width - m, 0, m, m),
        (0, height - m, m, m),
        (width - m, height - m, m, m),
    ]
    for grip, rect in zip(grips, rects):
        grip.setGeometry(*rect)
        grip.setVisible(visible)
        grip.raise_()
