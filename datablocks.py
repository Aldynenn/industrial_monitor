from __future__ import annotations

import json
from pathlib import Path


TYPE_SIZES = {
    "Bool": 1,
    "Byte": 1,
    "SInt": 1,
    "USInt": 1,
    "Word": 2,
    "Int": 2,
    "UInt": 2,
    "DWord": 4,
    "DInt": 4,
    "UDInt": 4,
    "Real": 4,
    "LReal": 8,
    "Time": 4,
}


def _ensure_log_flags(blocks: list[dict]) -> None:
    for block in blocks:
        fields = block.get("properties", {}).get("data", [])
        for field in fields:
            field["log"] = bool(field.get("log", False))
            interval_ms = int(field.get("log_interval_ms", 1000))
            field["log_interval_ms"] = max(1, interval_ms)


plc_datablocks = [
]


def calculate_offsets(variable_defs: list[dict]) -> list[dict]:
    """Return variables with automatically assigned byte/bit offsets."""
    calculated = []
    byte_offset = 0
    bit_offset = 0

    for var in variable_defs:
        var_name = var["name"]
        var_type = var["type"]
        var_log = bool(var.get("log", False))
        var_log_interval_ms = max(1, int(var.get("log_interval_ms", 1000)))

        if var_type == "Bool":
            calculated.append(
                {
                    "name": var_name,
                    "type": var_type,
                    "log": var_log,
                    "log_interval_ms": var_log_interval_ms,
                    "byte_offset": byte_offset,
                    "bit_offset": bit_offset,
                }
            )
            bit_offset += 1
            if bit_offset > 7:
                bit_offset = 0
                byte_offset += 1
            continue

        # Non-bool values start on the next whole byte boundary.
        if bit_offset != 0:
            bit_offset = 0
            byte_offset += 1

        size = TYPE_SIZES.get(var_type, 1)
        calculated.append(
            {
                "name": var_name,
                "type": var_type,
                "log": var_log,
                "log_interval_ms": var_log_interval_ms,
                "byte_offset": byte_offset,
                "bit_offset": 0,
            }
        )
        byte_offset += size

    return calculated


def save_plc_datablocks() -> None:
    """Persist current datablock definitions to datablocks_user.json."""
    config_path = Path(__file__).with_name("datablocks_user.json")
    config_path.write_text(json.dumps(plc_datablocks, indent=2), encoding="utf-8")


def load_plc_datablocks() -> None:
    """Load datablock definitions from datablocks_user.json if it exists."""
    config_path = Path(__file__).with_name("datablocks_user.json")
    if not config_path.exists():
        return

    try:
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return

    if isinstance(loaded, list):
        plc_datablocks.clear()
        plc_datablocks.extend(loaded)
        _ensure_log_flags(plc_datablocks)


    _ensure_log_flags(plc_datablocks)


load_plc_datablocks()