"""Command-line interface for Industrial Monitor.

Provides two subcommands:
    run      - headless mode: connect to PLC and start WebSocket server
    clients  - manage WebSocket client credentials
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from client_auth import ClientAuthStore

logger = logging.getLogger(__name__)


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
# Headless run (no Qt dependency)
# ---------------------------------------------------------------------------

def handle_run(args: argparse.Namespace) -> None:
    """Start PLC polling + WebSocket server without a GUI."""
    import threading

    from data_broker import DataBroker
    from config import SettingsStore
    from plc_communication import HeadlessPLCWorker
    from plc_data_logger import HeadlessPLCDataLogger
    from ws_server import WebSocketServer

    auth_store = ClientAuthStore()
    settings_store = SettingsStore()
    broker = DataBroker()

    data_logger = HeadlessPLCDataLogger(broker, settings_store)

    ws = WebSocketServer(broker, auth_store=auth_store,
                         settings_store=settings_store, port=args.port)
    ws.start()

    ip = args.ip
    rack = args.rack
    slot = args.slot

    done = threading.Event()

    def on_connected():
        logger.info("Connected to PLC at %s (rack=%s, slot=%s)", ip, rack, slot)

    def on_disconnected():
        logger.info("Disconnected from PLC.")
        done.set()

    auto_reconnect = getattr(args, 'auto_reconnect', False)

    def on_error(msg: str):
        logger.error("PLC error: %s", msg)
        if not auto_reconnect:
            done.set()

    worker = HeadlessPLCWorker(
        ip, rack, slot,
        broker=broker,
        on_connected=on_connected,
        on_disconnected=on_disconnected,
        on_error=on_error,
        auto_reconnect=auto_reconnect,
    )

    # Graceful shutdown on Ctrl+C
    def _shutdown(*_args):
        logger.info("Shutting down...")
        worker.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("Starting headless mode – PLC %s:%s/%s, WS port %s", ip, rack, slot, args.port)
    worker.start()

    done.wait()
    worker.join(timeout=3)
    data_logger.stop()


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
    run_parser.add_argument("--auto-reconnect", action="store_true", default=False,
                            help="Automatically reconnect to PLC on connection loss")

    # ---- clients ----
    clients_parser = sub.add_parser("clients", help="Manage WebSocket client credentials")
    client_sub = clients_parser.add_subparsers(dest="client_action")
    client_sub.required = True

    # clients list
    client_sub.add_parser("list", help="List all clients")

    # clients add
    add_p = client_sub.add_parser("add", help="Add a new client")
    add_p.add_argument("username", help="Client username")
    add_p.add_argument("password", help="Client password (min 8 chars, upper+lower+digit)")
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
    pw_p.add_argument("password", help="New password (min 8 chars, upper+lower+digit)")

    return parser


def main(argv: list[str] | None = None) -> None:
    from config import SettingsStore

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        # No subcommand -> launch GUI (handled by caller in main.py)
        return None

    # Apply config defaults for 'run' where not overridden
    if args.command == "run":
        plc_defaults = SettingsStore().get_plc()
        if args.ip is None:
            args.ip = plc_defaults["ip_address"]
        if args.rack is None:
            args.rack = plc_defaults["rack"]
        if args.slot is None:
            args.slot = plc_defaults["slot"]
        handle_run(args)
    elif args.command == "clients":
        handle_clients(args)
