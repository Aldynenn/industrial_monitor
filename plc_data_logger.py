from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from logging.handlers import MemoryHandler
from pathlib import Path
from time import monotonic

from datablocks import plc_datablocks
from logging_config import LoggingSettingsStore

FLUSH_INTERVAL_MS = 500

logger = logging.getLogger(__name__)


class TSVFormatter(logging.Formatter):
    """Formats PLC data records as tab-separated timestamp/variable/value lines."""

    def format(self, record: logging.LogRecord) -> str:
        return f"{record.timestamp}\t{record.variable}\t{record.value}"


class _PLCDataLoggerBase:
    """Shared PLC data-logging logic (no framework dependency)."""

    def _init_logging(self, broker, settings_store: LoggingSettingsStore):
        self._broker = broker
        self._settings_store = settings_store
        self._last_logged_ms: dict[str, int] = {}

        self._data_logger = logging.getLogger("plc_data")
        self._data_logger.setLevel(logging.INFO)
        self._data_logger.propagate = False

        self._file_handler: logging.FileHandler | None = None
        self._memory_handler: MemoryHandler | None = None
        self._current_file: str | None = None

    def _ensure_handler(self, output_file: str, include_header: bool) -> None:
        """Set up or reconfigure the file handler when the output path changes."""
        if self._current_file == output_file and self._memory_handler is not None:
            return

        # Flush and remove old handlers
        for handler in self._data_logger.handlers[:]:
            handler.flush()
            handler.close()
            self._data_logger.removeHandler(handler)

        path = Path(output_file)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent / path

        path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = path.exists()

        self._file_handler = logging.FileHandler(str(path), mode="a", encoding="utf-8")
        self._file_handler.setFormatter(TSVFormatter())

        self._memory_handler = MemoryHandler(
            capacity=10000,
            flushLevel=logging.CRITICAL + 1,  # only flush via timer
            target=self._file_handler,
        )
        self._data_logger.addHandler(self._memory_handler)
        self._current_file = output_file

        if include_header and not file_exists:
            self._file_handler.stream.write("timestamp_utc_ms\tvariable\tvalue\n")

    def _on_data(self, data: dict) -> None:
        settings = self._settings_store.get()
        if not settings.get("enabled", False):
            return

        self._ensure_handler(
            str(settings.get("output_file", "plc_logs.log")),
            bool(settings.get("include_header", True)),
        )

        now_ms = int(monotonic() * 1000)
        now_dt = datetime.now(timezone.utc)
        timestamp = now_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        for block in plc_datablocks:
            db_name = block.get("properties", {}).get("name")
            if not db_name:
                continue

            db_values = data.get(db_name)
            if not isinstance(db_values, dict):
                continue

            fields = block.get("properties", {}).get("data", [])
            for field in fields:
                if not bool(field.get("log", False)):
                    continue

                field_name = field.get("name")
                if not field_name or field_name not in db_values:
                    continue

                interval_ms = int(field.get("log_interval_ms", 1000))
                if interval_ms < 1:
                    interval_ms = 1

                key = f"{db_name}.{field_name}"
                last_ms = self._last_logged_ms.get(key)
                if last_ms is not None and (now_ms - last_ms) < interval_ms:
                    continue

                self._data_logger.info(
                    "",
                    extra={
                        "timestamp": timestamp,
                        "variable": key,
                        "value": str(db_values[field_name]),
                    },
                )
                self._last_logged_ms[key] = now_ms

    def _flush(self) -> None:
        if self._memory_handler:
            self._memory_handler.flush()


class HeadlessPLCDataLogger(_PLCDataLoggerBase):
    """PLC data logger that uses a background thread for periodic flushing (no Qt)."""

    def __init__(self, broker, settings_store: LoggingSettingsStore):
        self._init_logging(broker, settings_store)
        self._broker.data_updated.connect(self._on_data)
        self._stop_event = threading.Event()
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    def _flush_loop(self):
        while not self._stop_event.wait(FLUSH_INTERVAL_MS / 1000):
            self._flush()

    def stop(self):
        self._stop_event.set()


# ---------------------------------------------------------------------------
# Qt-based data logger (only available when PyQt6 is installed)
# ---------------------------------------------------------------------------

try:
    from PyQt6.QtCore import QObject, QTimer

    class PLCDataLogger(QObject, _PLCDataLoggerBase):
        """PLC data logger using QTimer for periodic flushing (Qt GUI version)."""

        def __init__(self, broker, settings_store: LoggingSettingsStore, parent=None):
            super().__init__(parent)
            self._init_logging(broker, settings_store)
            self._broker.data_updated.connect(self._on_data)

            self._flush_timer = QTimer(self)
            self._flush_timer.setInterval(FLUSH_INTERVAL_MS)
            self._flush_timer.timeout.connect(self._flush)
            self._flush_timer.start()

except ImportError:
    pass
