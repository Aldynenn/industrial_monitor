from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction


class TrayIcon(QSystemTrayIcon):
    """System tray icon that keeps the app running when the window is closed."""

    def __init__(self, window, icon_path: str = "icon.png", parent=None):
        super().__init__(parent)
        self._window = window

        self.setIcon(QIcon(icon_path))
        self.setToolTip("Industrial Monitor")

        # Context menu - stored as instance attr to prevent garbage collection
        self._menu = QMenu()

        show_action = QAction("Show", self._menu)
        show_action.triggered.connect(self._show_window)
        self._menu.addAction(show_action)

        quit_action = QAction("Quit", self._menu)
        quit_action.triggered.connect(self._quit)
        self._menu.addAction(quit_action)

        self.setContextMenu(self._menu)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_window()

    def _show_window(self):
        self._window.showNormal()
        self._window.activateWindow()

    def _quit(self):
        self._window._force_quit = True
        self._window.close()
        QApplication.quit()
