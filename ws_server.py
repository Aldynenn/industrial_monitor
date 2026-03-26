import asyncio
import json
import logging
import threading
from pathlib import Path

from websockets.asyncio.server import serve

from client_auth import ClientAuthStore
from config import SettingsStore

logger = logging.getLogger(__name__)


class WebSocketServer:
    """Pushes latest PLC data to all connected WebSocket clients."""

    def __init__(
        self,
        broker,
        auth_store: ClientAuthStore,
        settings_store: SettingsStore,
        host: str = "0.0.0.0",
        port: int = 8765,
    ):
        self._broker = broker
        self._auth_store = auth_store
        self._settings_store = settings_store
        self._host = host
        self._port = port
        self._clients: set = set()
        self._authenticated_clients: set = set()
        self._client_usernames: dict = {}
        self._client_roles: dict = {}
        self._client_last_sent: dict = {}  # websocket -> last sent (filtered) data
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._visibility_config = self._load_visibility_config()

        # Subscribe to broker updates
        self._broker.data_updated.connect(self._on_data)

    def start(self):
        """Start the WebSocket server on a background daemon thread."""
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    async def _serve(self):
        async with serve(self._handler, self._host, self._port):
            logger.info("WebSocket server listening on ws://%s:%s", self._host, self._port)
            await asyncio.Future()  # run forever

    async def _handler(self, websocket):
        self._clients.add(websocket)
        try:
            await websocket.send(
                json.dumps(
                    {
                        "type": "auth_required",
                        "message": "Authenticate first to receive PLC data.",
                    }
                )
            )
            async for message in websocket:
                await self._on_client_message(websocket, message)
        finally:
            self._clients.discard(websocket)
            self._authenticated_clients.discard(websocket)
            self._client_usernames.pop(websocket, None)
            self._client_roles.pop(websocket, None)
            self._client_last_sent.pop(websocket, None)

    async def _on_client_message(self, websocket, message: str):
        """Handle an incoming message from a WebSocket client."""
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            await websocket.send(json.dumps({"type": "error", "message": "Invalid JSON payload."}))
            return

        msg_type = payload.get("type")
        if msg_type == "auth":
            username = str(payload.get("username", "")).strip()
            password = str(payload.get("password", ""))
            ok, info, role = self._auth_store.authenticate_client(username, password)
            if ok:
                self._authenticated_clients.add(websocket)
                self._client_usernames[websocket] = username
                self._client_roles[websocket] = role
                await websocket.send(
                    json.dumps(
                        {
                            "type": "auth",
                            "ok": True,
                            "role": role,
                            "can_configure": role == "admin",
                            "message": "Authenticated.",
                        }
                    )
                )
                await websocket.send(
                    json.dumps(
                        {
                            "type": "visibility_config",
                            "config": self._visibility_config,
                        }
                    )
                )
                latest = self._broker.latest
                if latest:
                    filtered = self._apply_visibility(latest, self._visibility_config)
                    self._client_last_sent[websocket] = filtered
                    await websocket.send(json.dumps({"type": "plc_data", "data": filtered, "full": True}, default=str))
            else:
                await websocket.send(json.dumps({"type": "auth", "ok": False, "message": info}))
            return

        if websocket not in self._authenticated_clients:
            await websocket.send(
                json.dumps(
                    {
                        "type": "error",
                        "message": "Authenticate before sending commands.",
                    }
                )
            )
            return

        if msg_type == "visibility_get":
            await websocket.send(
                json.dumps(
                    {
                        "type": "visibility_config",
                        "config": self._visibility_config,
                    }
                )
            )
            return

        if msg_type == "visibility_set":
            role = self._client_roles.get(websocket)
            if role != "admin":
                await websocket.send(
                    json.dumps(
                        {
                            "type": "error",
                            "message": "Admin role required for visibility updates.",
                        }
                    )
                )
                return

            config_payload = payload.get("config")
            if not isinstance(config_payload, dict):
                await websocket.send(
                    json.dumps(
                        {
                            "type": "error",
                            "message": "Visibility config must be an object.",
                        }
                    )
                )
                return

            self._visibility_config = self._normalize_visibility_config(config_payload)
            self._save_visibility_config(self._visibility_config)
            # Invalidate cached state so all clients get a full resend
            self._client_last_sent.clear()
            await websocket.send(
                json.dumps(
                    {
                        "type": "visibility_set",
                        "ok": True,
                        "message": "Visibility updated.",
                    }
                )
            )
            await self._broadcast(
                json.dumps(
                    {
                        "type": "visibility_config",
                        "config": self._visibility_config,
                    }
                )
            )
            latest = self._broker.latest
            if latest:
                await self._broadcast_data(latest)
            return

        logger.info("Received from %s: %s", self._client_usernames.get(websocket, '?'), payload)

    # -------------------- broker callback (called from Qt thread) --------------------

    def _on_data(self, data: dict):
        if not self._loop or not self._authenticated_clients:
            return
        asyncio.run_coroutine_threadsafe(self._broadcast_data(data), self._loop)

    async def _broadcast(self, message: str):
        for ws in list(self._authenticated_clients):
            try:
                await ws.send(message)
            except Exception:
                self._clients.discard(ws)
                self._client_usernames.pop(ws, None)
                self._client_roles.pop(ws, None)
                self._client_last_sent.pop(ws, None)
                self._authenticated_clients.discard(ws)

    async def _broadcast_data(self, data: dict):
        filtered = self._apply_visibility(data, self._visibility_config)
        for ws in list(self._authenticated_clients):
            try:
                last = self._client_last_sent.get(ws)
                if last is None:
                    # First message for this client — send full snapshot
                    payload = json.dumps({"type": "plc_data", "data": filtered, "full": True}, default=str)
                else:
                    delta = self._compute_delta(last, filtered)
                    if not delta:
                        continue  # nothing changed for this client
                    payload = json.dumps({"type": "plc_data", "data": delta}, default=str)
                self._client_last_sent[ws] = filtered
                await ws.send(payload)
            except Exception:
                self._clients.discard(ws)
                self._client_usernames.pop(ws, None)
                self._client_roles.pop(ws, None)
                self._client_last_sent.pop(ws, None)
                self._authenticated_clients.discard(ws)

    @staticmethod
    def _compute_delta(old: dict, new: dict) -> dict:
        """Return only db/field entries whose values differ between old and new."""
        delta: dict = {}
        for db_name, new_fields in new.items():
            if not isinstance(new_fields, dict):
                continue
            old_fields = old.get(db_name)
            if not isinstance(old_fields, dict):
                # Entire db is new
                delta[db_name] = new_fields
                continue
            changed = {
                field: value
                for field, value in new_fields.items()
                if old_fields.get(field) != value
            }
            if changed:
                delta[db_name] = changed
        return delta

    def _load_visibility_config(self) -> dict:
        raw = self._settings_store.get_ws_visibility()
        if not isinstance(raw, dict):
            return {}
        return self._normalize_visibility_config(raw)

    def _save_visibility_config(self, config: dict) -> None:
        try:
            self._settings_store.update_ws_visibility(config)
        except Exception as exc:
            logger.error("Failed to save visibility config: %s", exc)

    def _normalize_visibility_config(self, config: dict) -> dict:
        normalized: dict = {}
        for db_name, fields in config.items():
            if not isinstance(db_name, str) or not isinstance(fields, dict):
                continue
            normalized[db_name] = {
                field_name: bool(is_visible)
                for field_name, is_visible in fields.items()
                if isinstance(field_name, str)
            }
        return normalized

    def _build_visibility_from_data(self, data: dict) -> dict:
        built: dict = {}
        for db_name, fields in data.items():
            if not isinstance(db_name, str) or not isinstance(fields, dict):
                continue
            built[db_name] = {field_name: True for field_name in fields.keys() if isinstance(field_name, str)}
        return built

    def _apply_visibility(self, data: dict, config: dict) -> dict:
        if not config:
            config = self._build_visibility_from_data(data)
            self._visibility_config = config
            self._save_visibility_config(config)

        filtered: dict = {}
        for db_name, fields in data.items():
            if not isinstance(fields, dict):
                continue
            db_config = config.get(db_name, {})
            filtered_fields = {
                field_name: value
                for field_name, value in fields.items()
                if db_config.get(field_name, True)
            }
            if filtered_fields:
                filtered[db_name] = filtered_fields
        return filtered
