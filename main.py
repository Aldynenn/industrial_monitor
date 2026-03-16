import sys
from PyQt6.QtWidgets import QApplication

from client_auth import ClientAuthStore
from gui import MainWindow
from logging_config import LoggingSettingsStore
from tray_icon import TrayIcon
from ws_server import WebSocketServer


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    auth_store = ClientAuthStore()
    logging_settings_store = LoggingSettingsStore()
    window = MainWindow(auth_store=auth_store, logging_settings_store=logging_settings_store)

    tray = TrayIcon(window)
    tray.show()
    window._tray = tray

    ws = WebSocketServer(window.broker, auth_store=auth_store, port=8765)
    ws.start()

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()