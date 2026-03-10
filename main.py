import sys
from PyQt6.QtWidgets import QApplication

from gui import MainWindow
from tray_icon import TrayIcon
from ws_server import WebSocketServer


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = MainWindow()

    tray = TrayIcon(window)
    tray.show()
    window._tray = tray

    ws = WebSocketServer(window.broker, port=8765)
    ws.start()

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()