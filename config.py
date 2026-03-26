from __future__ import annotations

import json
import threading
from pathlib import Path

DEFAULTS: dict = {
    "plc": {
        "ip_address": "192.168.0.27",
        "rack": 0,
        "slot": 1,
        "polling_interval_ms": 20,
    },
    "logging": {
        "enabled": False,
        "output_file": "plc_logs.log",
        "include_header": True,
    },
    "ws_visibility": {},
}


class SettingsStore:
    """Unified, thread-safe settings store backed by settings.json."""

    def __init__(self, settings_path: Path | None = None):
        self._path = settings_path or Path(__file__).with_name("settings.json")
        self._lock = threading.Lock()
        self._settings: dict = _deep_copy(DEFAULTS)
        self.load()

    def load(self) -> None:
        with self._lock:
            if not self._path.exists():
                return
            try:
                loaded = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                return
            if not isinstance(loaded, dict):
                return
            self._settings = _merge(DEFAULTS, loaded)

    def save(self) -> None:
        with self._lock:
            self._save_locked()

    def get(self) -> dict:
        with self._lock:
            return _deep_copy(self._settings)

    # ---- PLC section ----

    def get_plc(self) -> dict:
        with self._lock:
            return dict(self._settings["plc"])

    def update_plc(
        self, *, ip_address: str, rack: int, slot: int, polling_interval_ms: int
    ) -> None:
        with self._lock:
            self._settings["plc"] = {
                "ip_address": ip_address.strip(),
                "rack": int(rack),
                "slot": int(slot),
                "polling_interval_ms": max(1, int(polling_interval_ms)),
            }
            self._save_locked()

    # ---- Logging section ----

    def get_logging(self) -> dict:
        with self._lock:
            return dict(self._settings["logging"])

    def update_logging(
        self, *, enabled: bool, output_file: str, include_header: bool
    ) -> None:
        output = output_file.strip()
        if not output:
            raise ValueError("Output file path is required.")
        with self._lock:
            self._settings["logging"] = {
                "enabled": bool(enabled),
                "output_file": output,
                "include_header": bool(include_header),
            }
            self._save_locked()

    # ---- WebSocket visibility section ----

    def get_ws_visibility(self) -> dict:
        with self._lock:
            return _deep_copy(self._settings.get("ws_visibility", {}))

    def update_ws_visibility(self, config: dict) -> None:
        with self._lock:
            self._settings["ws_visibility"] = _deep_copy(config)
            self._save_locked()

    # ---- Internal ----

    def _save_locked(self) -> None:
        """Write settings to disk (caller must hold self._lock)."""
        self._path.write_text(
            json.dumps(self._settings, indent=2), encoding="utf-8"
        )


def _deep_copy(d: dict) -> dict:
    return json.loads(json.dumps(d))


def _merge(defaults: dict, loaded: dict) -> dict:
    """Merge loaded values over defaults, section by section."""
    result = _deep_copy(defaults)
    for key, default_val in defaults.items():
        if key not in loaded:
            continue
        if isinstance(default_val, dict) and isinstance(loaded[key], dict):
            merged_section = dict(default_val)
            merged_section.update(loaded[key])
            result[key] = merged_section
        else:
            result[key] = loaded[key]
    return result