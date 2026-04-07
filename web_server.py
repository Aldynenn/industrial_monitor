import logging
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

logger = logging.getLogger(__name__)

_WEBSITE_DIR = Path(__file__).with_name("website")


class _SilentHandler(SimpleHTTPRequestHandler):
    """Serves static files without logging each HTTP request."""

    def log_message(self, format, *args):
        pass


class StaticWebServer:
    """Serves the website/ directory on a configurable port."""

    def __init__(self, host="0.0.0.0", port=8080):
        self._host = host
        self._port = port
        self._thread: threading.Thread | None = None
        handler = partial(_SilentHandler, directory=str(_WEBSITE_DIR))
        self._server = HTTPServer((self._host, self._port), handler)

    def start(self):
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("Static web server listening on http://%s:%s", self._host, self._port)

    def stop(self):
        self._server.shutdown()
