import asyncio
import json
import threading

from websockets.asyncio.server import serve

from data_broker import DataBroker


class WebSocketServer:
    """Pushes latest PLC data to all connected WebSocket clients."""

    def __init__(self, broker: DataBroker, host: str = "0.0.0.0", port: int = 8765):
        self._broker = broker
        self._host = host
        self._port = port
        self._clients: set = set()
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
            async for message in websocket:
                self._on_client_message(message)
        finally:
            self._clients.discard(websocket)

    def _on_client_message(self, message: str):
        """Handle an incoming message from a WebSocket client."""
        print(f"[WS] Received: {message}")

    # -------------------- broker callback (called from Qt thread) --------------------

    def _on_data(self, data: dict):
        if not self._loop or not self._clients:
            return
        payload = json.dumps(data, default=str)
        asyncio.run_coroutine_threadsafe(self._broadcast(payload), self._loop)

    async def _broadcast(self, message: str):
        for ws in list(self._clients):
            try:
                await ws.send(message)
            except Exception:
                self._clients.discard(ws)
