from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

from PyQt6.QtCore import QObject

from datablocks import plc_datablocks
from data_broker import DataBroker
from logging_config import LoggingSettingsStore


class PLCDataLogger(QObject):
    """Logs PLC variable values based on per-variable logging intervals."""

    def __init__(self, broker: DataBroker, settings_store: LoggingSettingsStore, parent=None):
        super().__init__(parent)
        self._broker = broker
        self._settings_store = settings_store
        self._last_logged_ms: dict[str, int] = {}
        self._broker.data_updated.connect(self._on_data)

    def _on_data(self, data: dict) -> None:
        settings = self._settings_store.get()
        if not settings.get("enabled", False):
            return

        rows: list[list[str]] = []
        now_ms = int(monotonic() * 1000)
        # Timestamp with ms precision in ISO format
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

                rows.append(
                    [
                        timestamp,
                        f"{db_name}.{field_name}",
                        str(db_values[field_name]),
                    ]
                )
                self._last_logged_ms[key] = now_ms

        if rows:
            self._append_rows(
                output_file=str(settings.get("output_file", "plc_logs.csv")),
                include_header=bool(settings.get("include_header", True)),
                rows=rows,
            )

    @staticmethod
    def _append_rows(output_file: str, include_header: bool, rows: list[list[str]]) -> None:
        path = Path(output_file)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent / path

        path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = path.exists()

        with path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            if include_header and not file_exists:
                writer.writerow(["timestamp_utc_ms", "variable", "value"])
            writer.writerows(rows)
