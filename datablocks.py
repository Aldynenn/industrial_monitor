from __future__ import annotations

import json
from pathlib import Path


TYPE_SIZES = {
    "Bool": 1,
    "Int": 2,
    "Time": 4,
}


def _ensure_log_flags(blocks: list[dict]) -> None:
    for block in blocks:
        fields = block.get("properties", {}).get("data", [])
        for field in fields:
            field["log"] = bool(field.get("log", False))


plc_datablocks = [
    {
        "db_number": 1, 
        "properties": {
            "name": "LED_states", 
            "data": [
                {"name": "el01", "type": "Bool", "byte_offset": 0, "bit_offset": 0},
                {"name": "el02", "type": "Bool", "byte_offset": 0, "bit_offset": 1},
                {"name": "el03", "type": "Bool", "byte_offset": 0, "bit_offset": 2},
                {"name": "el04", "type": "Bool", "byte_offset": 0, "bit_offset": 3},
                {"name": "el05", "type": "Bool", "byte_offset": 0, "bit_offset": 4},
                {"name": "el06", "type": "Bool", "byte_offset": 0, "bit_offset": 5},
                {"name": "el07", "type": "Bool", "byte_offset": 0, "bit_offset": 6},
                {"name": "el08", "type": "Bool", "byte_offset": 0, "bit_offset": 7},
                {"name": "eoff_signal", "type": "Bool", "byte_offset": 1, "bit_offset": 0},
                {"name": "etimer_duration", "type": "Time", "byte_offset": 2, "bit_offset": 0},
                {"name": "btn_green", "type": "Bool", "byte_offset": 6, "bit_offset": 0},
                {"name": "il01", "type": "Bool", "byte_offset": 6, "bit_offset": 1},
                {"name": "il02", "type": "Bool", "byte_offset": 6, "bit_offset": 2},
                {"name": "il03", "type": "Bool", "byte_offset": 6, "bit_offset": 3},
                {"name": "il04", "type": "Bool", "byte_offset": 6, "bit_offset": 4},
                {"name": "il05", "type": "Bool", "byte_offset": 6, "bit_offset": 5},
                {"name": "il06", "type": "Bool", "byte_offset": 6, "bit_offset": 6},
                {"name": "il07", "type": "Bool", "byte_offset": 6, "bit_offset": 7},
                {"name": "il08", "type": "Bool", "byte_offset": 7, "bit_offset": 0}
            ]
        }
    },
    {
        "db_number": 2, 
        "properties": {
            "name": "led_timer", 
            "data": [
                {"name": "PT", "type": "Time", "byte_offset": 4, "bit_offset": 0},
                {"name": "ET", "type": "Time", "byte_offset": 8, "bit_offset": 0},
                {"name": "IN", "type": "Bool", "byte_offset": 12, "bit_offset": 1},
                {"name": "Q", "type": "Bool", "byte_offset": 12, "bit_offset": 2}
            ]
        }
    },
    {
        "db_number": 3, 
        "properties": {
            "name": "led_pulse", 
            "data": [
                {"name": "PT", "type": "Time", "byte_offset": 4, "bit_offset": 0},
                {"name": "ET", "type": "Time", "byte_offset": 8, "bit_offset": 0},
                {"name": "IN", "type": "Bool", "byte_offset": 12, "bit_offset": 1},
                {"name": "Q", "type": "Bool", "byte_offset": 12, "bit_offset": 2}
            ]
        }
    },
    {
        "db_number": 4, 
        "properties": {
            "name": "led_counter",
            "data": [
                {"name": "CU", "type": "Bool", "byte_offset": 0, "bit_offset": 0},
                {"name": "CD", "type": "Bool", "byte_offset": 0, "bit_offset": 1},
                {"name": "R", "type": "Bool", "byte_offset": 0, "bit_offset": 2},
                {"name": "LD", "type": "Bool", "byte_offset": 0, "bit_offset": 3},
                {"name": "QU", "type": "Bool", "byte_offset": 0, "bit_offset": 4},
                {"name": "QD", "type": "Bool", "byte_offset": 0, "bit_offset": 5},
                {"name": "PV", "type": "Int", "byte_offset": 2, "bit_offset": 0},
                {"name": "CV", "type": "Int", "byte_offset": 4, "bit_offset": 0}
            ]
        }
    },
    {
        "db_number": 5, 
        "properties": {
            "name": "flash_timer_01",
            "data": [
                {"name": "PT", "type": "Time", "byte_offset": 4, "bit_offset": 0},
                {"name": "ET", "type": "Time", "byte_offset": 8, "bit_offset": 0},
                {"name": "IN", "type": "Bool", "byte_offset": 12, "bit_offset": 1},
                {"name": "Q", "type": "Bool", "byte_offset": 12, "bit_offset": 2}
            ]
        }
    },
    {
        "db_number": 6,
        "properties": {
            "name": "flash_timer_off_01",
            "data": [
                {"name": "PT", "type": "Time", "byte_offset": 4, "bit_offset": 0},
                {"name": "ET", "type": "Time", "byte_offset": 8, "bit_offset": 0},
                {"name": "IN", "type": "Bool", "byte_offset": 12, "bit_offset": 1},
                {"name": "Q", "type": "Bool", "byte_offset": 12, "bit_offset": 2}
            ]
        }
    },
    {
        "db_number": 7,
        "properties": {
            "name": "flash_timer_02",
            "data": [
                {"name": "PT", "type": "Time", "byte_offset": 4, "bit_offset": 0},
                {"name": "ET", "type": "Time", "byte_offset": 8, "bit_offset": 0},
                {"name": "IN", "type": "Bool", "byte_offset": 12, "bit_offset": 1},
                {"name": "Q", "type": "Bool", "byte_offset": 12, "bit_offset": 2}
            ]
        }
    },
    {
        "db_number": 8,
        "properties": {
            "name": "flash_timer_off_02",
            "data": [
                {"name": "PT", "type": "Time", "byte_offset": 4, "bit_offset": 0},
                {"name": "ET", "type": "Time", "byte_offset": 8, "bit_offset": 0},
                {"name": "IN", "type": "Bool", "byte_offset": 12, "bit_offset": 1},
                {"name": "Q", "type": "Bool", "byte_offset": 12, "bit_offset": 2}
            ]
        }
    }
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

        if var_type == "Bool":
            calculated.append(
                {
                    "name": var_name,
                    "type": var_type,
                    "log": var_log,
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