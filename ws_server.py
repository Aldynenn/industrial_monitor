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
        self._user_visibility_cache: dict = {}  # username -> normalized visibility config
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._visibility_config = self._load_visibility_config()  # global default

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

    def stop(self):
        """Gracefully shut down the WebSocket server."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=3)
            logger.info("WebSocket server stopped.")

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
                            "username": username,
                            "config": self._get_effective_visibility(username),
                        }
                    )
                )
                viz = self._auth_store.get_user_visualization(username)
                await websocket.send(
                    json.dumps(
                        {
                            "type": "graphs_config",
                            "username": username,
                            "graphs": viz["graphs"],
                            "boolActiveColors": viz["boolActiveColors"],
                        }
                    )
                )
                latest = self._broker.latest
                if latest:
                    user_vis = self._get_effective_visibility(username)
                    filtered = self._apply_visibility(latest, user_vis)
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
            caller_role = self._client_roles.get(websocket)
            caller_name = self._client_usernames.get(websocket, "")
            target = str(payload.get("username", "")).strip()
            if target and target != caller_name and caller_role != "admin":
                await websocket.send(
                    json.dumps({"type": "error", "message": "Admin role required to view other users' visibility."})
                )
                return
            username = target if target else caller_name
            await websocket.send(
                json.dumps(
                    {
                        "type": "visibility_config",
                        "username": username,
                        "config": self._get_effective_visibility(username),
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

            target = str(payload.get("username", "")).strip()
            if not target:
                await websocket.send(
                    json.dumps(
                        {
                            "type": "error",
                            "message": "Target username is required.",
                        }
                    )
                )
                return

            normalized = self._normalize_visibility_config(config_payload)
            self._auth_store.set_user_visibility(target, normalized)
            self._user_visibility_cache[target] = normalized
            # Invalidate cached state for this user's connections so they get a full resend
            for ws in list(self._authenticated_clients):
                if self._client_usernames.get(ws) == target:
                    self._client_last_sent.pop(ws, None)
            await websocket.send(
                json.dumps(
                    {
                        "type": "visibility_set",
                        "ok": True,
                        "message": f"Visibility updated for '{target}'.",
                    }
                )
            )
            # Push updated config to the target user if they're connected
            for ws in list(self._authenticated_clients):
                if self._client_usernames.get(ws) == target:
                    try:
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "visibility_config",
                                    "username": target,
                                    "config": normalized,
                                }
                            )
                        )
                    except Exception:
                        pass
            # Re-broadcast data with new filtering for affected user
            latest = self._broker.latest
            if latest:
                await self._broadcast_data(latest)
            return

        if msg_type == "graphs_get":
            target = str(payload.get("username", "")).strip()
            caller_role = self._client_roles.get(websocket)
            caller_name = self._client_usernames.get(websocket, "")
            if target and target != caller_name and caller_role != "admin":
                await websocket.send(
                    json.dumps({"type": "error", "message": "Admin role required to view other users' graphs."})
                )
                return
            username = target if target else caller_name
            viz = self._auth_store.get_user_visualization(username)
            await websocket.send(
                json.dumps({"type": "graphs_config", "username": username, "graphs": viz["graphs"], "boolActiveColors": viz["boolActiveColors"]})
            )
            return

        if msg_type == "graphs_set":
            caller_role = self._client_roles.get(websocket)
            if caller_role != "admin":
                await websocket.send(
                    json.dumps({"type": "error", "message": "Admin role required to manage graphs."})
                )
                return
            target = str(payload.get("username", "")).strip()
            if not target:
                await websocket.send(
                    json.dumps({"type": "error", "message": "Target username is required."})
                )
                return
            graphs = payload.get("graphs")
            bool_colors = payload.get("boolActiveColors")
            if not isinstance(graphs, list):
                await websocket.send(
                    json.dumps({"type": "error", "message": "graphs must be an array."})
                )
                return
            if not isinstance(bool_colors, dict):
                bool_colors = {}
            self._auth_store.set_user_visualization(target, graphs, bool_colors)
            await websocket.send(
                json.dumps({"type": "graphs_set", "ok": True, "message": f"Graphs saved for '{target}'."})
            )
            # Push updated config to the target user if they're connected
            for ws in list(self._authenticated_clients):
                if self._client_usernames.get(ws) == target:
                    try:
                        await ws.send(
                            json.dumps({"type": "graphs_config", "username": target, "graphs": graphs, "boolActiveColors": bool_colors})
                        )
                    except Exception:
                        pass
            return

        if msg_type == "users_list":
            caller_role = self._client_roles.get(websocket)
            if caller_role != "admin":
                await websocket.send(
                    json.dumps({"type": "error", "message": "Admin role required."})
                )
                return
            usernames = self._auth_store.list_usernames()
            await websocket.send(
                json.dumps({"type": "users_list", "usernames": usernames})
            )
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
        for ws in list(self._authenticated_clients):
            try:
                username = self._client_usernames.get(ws, "")
                user_vis = self._get_effective_visibility(username)
                filtered = self._apply_visibility(data, user_vis)
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

    def _get_effective_visibility(self, username: str) -> dict:
        """Return per-user visibility config, falling back to the global default."""
        if username in self._user_visibility_cache:
            return self._user_visibility_cache[username]
        per_user = self._auth_store.get_user_visibility(username)
        if per_user:
            normalized = self._normalize_visibility_config(per_user)
            self._user_visibility_cache[username] = normalized
            return normalized
        return self._visibility_config

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
