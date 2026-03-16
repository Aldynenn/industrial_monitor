import asyncio
import json
import threading

from websockets.asyncio.server import serve

from client_auth import ClientAuthStore
from data_broker import DataBroker


class WebSocketServer:
    """Pushes latest PLC data to all connected WebSocket clients."""

    def __init__(
        self,
        broker: DataBroker,
        auth_store: ClientAuthStore,
        host: str = "0.0.0.0",
        port: int = 8765,
    ):
        self._broker = broker
        self._auth_store = auth_store
        self._host = host
        self._port = port
        self._clients: set = set()
        self._authenticated_clients: set = set()
        self._client_usernames: dict = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

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
            print(f"WebSocket server listening on ws://{self._host}:{self._port}")
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
            ok, info = self._auth_store.authenticate_client(username, password)
            if ok:
                self._authenticated_clients.add(websocket)
                self._client_usernames[websocket] = username
                await websocket.send(
                    json.dumps({"type": "auth", "ok": True, "message": "Authenticated."})
                )
                latest = self._broker.latest
                if latest:
                    await websocket.send(json.dumps({"type": "plc_data", "data": latest}, default=str))
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

        print(f"[WS] Received from {self._client_usernames.get(websocket, '?')}: {payload}")

    # -------------------- broker callback (called from Qt thread) --------------------

    def _on_data(self, data: dict):
        if not self._loop or not self._authenticated_clients:
            return
        payload = json.dumps({"type": "plc_data", "data": data}, default=str)
        asyncio.run_coroutine_threadsafe(self._broadcast(payload), self._loop)

    async def _broadcast(self, message: str):
        for ws in list(self._authenticated_clients):
            try:
                await ws.send(message)
            except Exception:
                self._clients.discard(ws)
                self._client_usernames.pop(ws, None)
                self._authenticated_clients.discard(ws)
