"""Windows notifications through the system tray.

On Windows, QSystemTrayIcon.showMessage() shows a native notification, even when the launcher
is minimised. A notification is sent only when the launcher window is not in use, so it does
not interrupt someone who is already looking at it. If the system has no tray (some remote
desktops, some Linux setups), notifications are skipped silently.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..app.version import APP_NAME


class Notifier(QObject):
    def __init__(self, icon: QIcon, window, enabled: Callable[[], bool], parent=None) -> None:
        super().__init__(parent)
        self._window = window
        self._enabled = enabled
        self._tray: QSystemTrayIcon | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = QSystemTrayIcon(icon, self)
            self._tray.setToolTip(APP_NAME)
            menu = QMenu()
            menu.addAction("Open Nolde Launcher", self._show_window)
            menu.addSeparator()
            menu.addAction("Exit", window.close)
            self._tray.setContextMenu(menu)
            self._tray.activated.connect(self._on_activated)

    @property
    def available(self) -> bool:
        return self._tray is not None

    def set_enabled(self, flag: bool) -> None:
        """The tray icon is shown only while notifications are on."""
        if self._tray is None:
            return
        if flag:
            self._tray.show()
        else:
            self._tray.hide()

    def notify(self, title: str, message: str, timeout_ms: int = 6000) -> bool:
        if self._tray is None or not self._enabled() or self._window_in_use():
            return False
        self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, timeout_ms)
        return True

    def _window_in_use(self) -> bool:
        return self._window.isActiveWindow() and not self._window.isMinimized()

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._show_window()

    def _show_window(self) -> None:
        self._window.showNormal()
        self._window.raise_()
        self._window.activateWindow()
