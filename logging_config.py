from __future__ import annotations

import json
import threading
from pathlib import Path


DEFAULT_LOG_SETTINGS = {
    "enabled": False,
    "output_file": "plc_logs.log",
    "include_header": True,
}


class LoggingSettingsStore:
    """Stores and persists global PLC logging settings."""

    def __init__(self, settings_path: Path | None = None):
        self._settings_path = settings_path or Path(__file__).with_name("logging_settings.json")
        self._lock = threading.Lock()
        self._settings = dict(DEFAULT_LOG_SETTINGS)
        self.load()

    def load(self) -> None:
        with self._lock:
            if not self._settings_path.exists():
                return

            try:
                loaded = json.loads(self._settings_path.read_text(encoding="utf-8"))
            except Exception:
                return

            if not isinstance(loaded, dict):
                return

            merged = dict(DEFAULT_LOG_SETTINGS)
            merged.update(loaded)
            merged["enabled"] = bool(merged.get("enabled", False))
            merged["output_file"] = str(merged.get("output_file", DEFAULT_LOG_SETTINGS["output_file"])).strip() or DEFAULT_LOG_SETTINGS["output_file"]
            merged["include_header"] = bool(merged.get("include_header", True))
            self._settings = merged

    def save(self) -> None:
        with self._lock:
            self._settings_path.write_text(json.dumps(self._settings, indent=2), encoding="utf-8")

    def get(self) -> dict:
        with self._lock:
            return dict(self._settings)

    def update(self, *, enabled: bool, output_file: str, include_header: bool) -> None:
        output = output_file.strip()
        if not output:
            raise ValueError("Output file path is required.")

        with self._lock:
            self._settings = {
                "enabled": bool(enabled),
                "output_file": output,
                "include_header": bool(include_header),
            }
            self._settings_path.write_text(json.dumps(self._settings, indent=2), encoding="utf-8")
