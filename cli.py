"""Command-line interface for Industrial Monitor.

Provides two subcommands:
    run      - headless mode: connect to PLC and start WebSocket server
    clients  - manage WebSocket client credentials
"""

from __future__ import annotations

import argparse
import signal
import sys

from client_auth import ClientAuthStore


# ---------------------------------------------------------------------------
# Client management (no Qt required)
# ---------------------------------------------------------------------------

def _clients_list(auth_store: ClientAuthStore) -> None:
    clients = auth_store.list_clients()
    if not clients:
        print("No clients found.")
        return

    header = f"{'ID':>4}  {'Username':<20}  {'Role':<6}  {'Active':<6}  {'Created':<25}  {'Last Auth':<25}"
    print(header)
    print("-" * len(header))
    for c in clients:
        active = "Yes" if c["is_active"] else "No"
        last_auth = c["last_auth_at"] or "Never"
        print(f"{c['id']:>4}  {c['username']:<20}  {c['role']:<6}  {active:<6}  {c['created_at']:<25}  {last_auth:<25}")


def _clients_add(auth_store: ClientAuthStore, username: str, password: str, role: str) -> None:
    try:
        auth_store.add_client(username, password, role)
        print(f"Client '{username}' added with role '{role}'.")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _clients_delete(auth_store: ClientAuthStore, client_id: int) -> None:
    auth_store.delete_client(client_id)
    print(f"Client {client_id} deleted.")


def _clients_enable(auth_store: ClientAuthStore, client_id: int) -> None:
    auth_store.set_active(client_id, True)
    print(f"Client {client_id} enabled.")


def _clients_disable(auth_store: ClientAuthStore, client_id: int) -> None:
    auth_store.set_active(client_id, False)
    print(f"Client {client_id} disabled.")


def _clients_set_role(auth_store: ClientAuthStore, client_id: int, role: str) -> None:
    try:
        auth_store.set_role(client_id, role)
        print(f"Client {client_id} role set to '{role}'.")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _clients_set_password(auth_store: ClientAuthStore, client_id: int, password: str) -> None:
    try:
        auth_store.update_password(client_id, password)
        print(f"Client {client_id} password updated.")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def handle_clients(args: argparse.Namespace) -> None:
    """Dispatch client subcommands."""
    auth_store = ClientAuthStore()
    action = args.client_action

    if action == "list":
        _clients_list(auth_store)
    elif action == "add":
        _clients_add(auth_store, args.username, args.password, args.role)
    elif action == "delete":
        _clients_delete(auth_store, args.id)
    elif action == "enable":
        _clients_enable(auth_store, args.id)
    elif action == "disable":
        _clients_disable(auth_store, args.id)
    elif action == "set-role":
        _clients_set_role(auth_store, args.id, args.role)
    elif action == "set-password":
        _clients_set_password(auth_store, args.id, args.password)


# ---------------------------------------------------------------------------
# Headless run (requires Qt core for QThread / signals)
# ---------------------------------------------------------------------------

def handle_run(args: argparse.Namespace) -> None:
    """Start PLC polling + WebSocket server without a GUI."""
    from PyQt6.QtCore import QCoreApplication, QTimer

    from data_broker import DataBroker
    from logging_config import LoggingSettingsStore
    from plc_communication import PLCWorker
    from plc_data_logger import PLCDataLogger
    from ws_server import WebSocketServer

    app = QCoreApplication(sys.argv)

    auth_store = ClientAuthStore()
    logging_settings_store = LoggingSettingsStore()
    broker = DataBroker()

    _data_logger = PLCDataLogger(broker, logging_settings_store)

    ws = WebSocketServer(broker, auth_store=auth_store, port=args.port)
    ws.start()

    ip = args.ip
    rack = args.rack
    slot = args.slot

    worker = PLCWorker(ip, rack, slot, broker=broker)

    def on_connected():
        print(f"Connected to PLC at {ip} (rack={rack}, slot={slot})")

    def on_disconnected():
        print("Disconnected from PLC.")
        app.quit()

    def on_error(msg: str):
        print(f"PLC error: {msg}", file=sys.stderr)
        app.quit()

    worker.connected.connect(on_connected)
    worker.disconnected.connect(on_disconnected)
    worker.error_occurred.connect(on_error)
    worker.finished.connect(app.quit)

    # Graceful shutdown on Ctrl+C
    def _shutdown(*_args):
        print("\nShutting down...")
        worker.stop()
        worker.wait(3000)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Allow Python signal handlers to fire inside the Qt event loop
    timer = QTimer()
    timer.start(200)
    timer.timeout.connect(lambda: None)

    print(f"Starting headless mode – PLC {ip}:{rack}/{slot}, WS port {args.port}")
    worker.start()

    sys.exit(app.exec())


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="industrial_monitor",
        description="Industrial Monitor – PLC data acquisition and WebSocket server",
    )
    sub = parser.add_subparsers(dest="command")

    # ---- run ----
    run_parser = sub.add_parser("run", help="Start headless PLC polling and WebSocket server")
    run_parser.add_argument("--ip", default=None, help="PLC IP address (default: from config)")
    run_parser.add_argument("--rack", type=int, default=None, help="PLC rack number (default: from config)")
    run_parser.add_argument("--slot", type=int, default=None, help="PLC slot number (default: from config)")
    run_parser.add_argument("--port", type=int, default=8765, help="WebSocket server port (default: 8765)")

    # ---- clients ----
    clients_parser = sub.add_parser("clients", help="Manage WebSocket client credentials")
    client_sub = clients_parser.add_subparsers(dest="client_action")
    client_sub.required = True

    # clients list
    client_sub.add_parser("list", help="List all clients")

    # clients add
    add_p = client_sub.add_parser("add", help="Add a new client")
    add_p.add_argument("username", help="Client username")
    add_p.add_argument("password", help="Client password (min 4 chars)")
    add_p.add_argument("--role", default="user", choices=["user", "admin"], help="Client role (default: user)")

    # clients delete
    del_p = client_sub.add_parser("delete", help="Delete a client by ID")
    del_p.add_argument("id", type=int, help="Client ID")

    # clients enable
    en_p = client_sub.add_parser("enable", help="Enable a client")
    en_p.add_argument("id", type=int, help="Client ID")

    # clients disable
    dis_p = client_sub.add_parser("disable", help="Disable a client")
    dis_p.add_argument("id", type=int, help="Client ID")

    # clients set-role
    role_p = client_sub.add_parser("set-role", help="Change a client's role")
    role_p.add_argument("id", type=int, help="Client ID")
    role_p.add_argument("role", choices=["user", "admin"], help="New role")

    # clients set-password
    pw_p = client_sub.add_parser("set-password", help="Update a client's password")
    pw_p.add_argument("id", type=int, help="Client ID")
    pw_p.add_argument("password", help="New password (min 4 chars)")

    return parser


def main(argv: list[str] | None = None) -> None:
    import config

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        # No subcommand -> launch GUI (handled by caller in main.py)
        return None

    # Apply config defaults for 'run' where not overridden
    if args.command == "run":
        if args.ip is None:
            args.ip = config.DEFAULT_IP_ADDRESS
        if args.rack is None:
            args.rack = config.DEFAULT_RACK_NUMBER
        if args.slot is None:
            args.slot = config.DEFAULT_SLOT_NUMBER
        handle_run(args)
    elif args.command == "clients":
        handle_clients(args)
