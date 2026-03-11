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
                {"name": "btn_green", "type": "Bool", "byte_offset": 6, "bit_offset": 0}
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