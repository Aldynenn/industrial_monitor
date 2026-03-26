import logging
import sys


def main_gui():
    from PyQt6.QtWidgets import QApplication

    from client_auth import ClientAuthStore
    from gui import MainWindow
    from logging_config import LoggingSettingsStore
    from tray_icon import TrayIcon
    from ws_server import WebSocketServer

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


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    from cli import build_parser, main as cli_main

    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        # No subcommand → launch GUI
        main_gui()
    else:
        cli_main(sys.argv[1:])


if __name__ == "__main__":
    main()