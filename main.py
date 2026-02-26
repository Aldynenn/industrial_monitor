import snap7
from snap7.util import get_bool, get_time, get_dword
from snap7.type import Areas
import time

PLC_IP = "192.168.0.27"
RACK = 0
SLOT = 1

plc = snap7.client.Client()
plc.connect(PLC_IP, RACK, SLOT)

def read_db_values(plc: snap7.client.Client, db_number: int, db_start: int, db_size: int):
    buf = plc.read_area(Areas.DB, db_number, db_start, db_size)

    values = {
        "el01": 1 if get_bool(buf, 0, 0) else 0,
        "el02": 1 if get_bool(buf, 0, 1) else 0,
        "el03": 1 if get_bool(buf, 0, 2) else 0,
        "el04": 1 if get_bool(buf, 0, 3) else 0,
        "el05": 1 if get_bool(buf, 0, 4) else 0,
        "el06": 1 if get_bool(buf, 0, 5) else 0,
        "el07": 1 if get_bool(buf, 0, 6) else 0,
        "el08": 1 if get_bool(buf, 0, 7) else 0,
        "eoff_signal": 1 if get_bool(buf, 1, 0) else 0,
        # TIME is 4 bytes starting at byte 2
        # returns a string like '0:0:0.100' for T#100ms [web:25][web:30]
        "etimer_duration": get_time(buf, 2),
        "btn_green": 1 if get_bool(buf, 6, 0) else 0,
    }
    return values

def read_db5_values(plc: snap7.client.Client, db_number: int, db_start: int, db_size: int):
    buf = plc.read_area(Areas.DB, db_number, db_start, db_size)

    values = {
        "etimer_duration": get_time(buf, 0),
        "etimer_duration": get_time(buf, 4),
        "in": 1 if get_bool(buf, 8, 1) else 0,
        "q": 1 if get_bool(buf, 8, 2) else 0,
    }
    return values


DB_NUMBER = 1
DB_START = 0
DB_SIZE = 7
avg_loop_time = 0

while True:
    loop_start_time = time.time()
    
    data = read_db_values(plc, 1, 0, 7)
    print(f"{data}\r", end='')  # Carriage return to overwrite the same line
    
    loop_end_time = time.time()
    loop_time = loop_end_time - loop_start_time