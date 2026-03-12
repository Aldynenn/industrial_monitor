import snap7
from PyQt6.QtCore import QThread, pyqtSignal

import config
from datablocks import plc_datablocks

class PLCCommunication:
    connection_error = False

    def __init__(self, ip_address, rack, slot):
        self.plc = snap7.client.Client()
        try:
            self.plc.connect(ip_address, rack, slot)
            self.connection_error = self.plc.get_connected()
            print(f"Connected to PLC: {self.connection_error}")
        except Exception as e:
            print(f"Error connecting to PLC: {e}")
            self.connection_error = True

    def disconnect(self):
        self.plc.disconnect()

    def read_boolean(self, db_number, start_offset, bit_offset):
        reading = self.plc.db_read(db_number, start_offset, 1)
        return snap7.util.get_bool(reading, 0, bit_offset)

    def read_int(self, db_number, start_offset):
        reading = self.plc.db_read(db_number, start_offset, 2)
        return snap7.util.get_int(reading, 0)

    def read_time(self, db_number, start_offset):
        reading = self.plc.db_read(db_number, start_offset, 4)
        return snap7.util.get_dword(reading, 0)

    def read_db_range(self, db_number, start, size):
        return self.plc.db_read(db_number, start, size)


class PLCWorker(QThread):
    """Worker thread that polls PLC data periodically."""

    error_occurred = pyqtSignal(str)
    connected = pyqtSignal()
    disconnected = pyqtSignal()

    def __init__(self, ip: str, rack: int, slot: int, broker=None):
        super().__init__()
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self._running = False
        self.plc: PLCCommunication | None = None
        self._broker = broker

    def run(self):
        try:
            self.plc = PLCCommunication(self.ip, self.rack, self.slot)
            if self.plc.connection_error and not self.plc.plc.get_connected():
                self.error_occurred.emit("Failed to connect to PLC.")
                return
            self.connected.emit()
        except Exception as e:
            self.error_occurred.emit(str(e))
            return

        self._running = True
        while self._running:
            try:
                data = self._read_db_values()
                if self._broker:
                    self._broker.update(data)
            except Exception as e:
                self.error_occurred.emit(str(e))
                self._running = False
                break
            self.msleep(config.POLLING_INTERVAL_MS)

        # cleanup
        try:
            if self.plc:
                self.plc.disconnect()
        except Exception:
            pass
        self.disconnected.emit()

    def stop(self):
        self._running = False

    _type_sizes = {"Bool": 1, "Int": 2, "Time": 4}

    _field_parsers = {
        "Bool": lambda buf, field, base: snap7.util.get_bool(buf, field["byte_offset"] - base, field["bit_offset"]),
        "Int": lambda buf, field, base: snap7.util.get_int(buf, field["byte_offset"] - base),
        "Time": lambda buf, field, base: snap7.util.get_dword(buf, field["byte_offset"] - base),
    }

    def _read_db_values(self) -> dict:
        """Read all datablock values defined in datablocks.py.

        Each DB is read in a single db_read call covering the full byte range
        of its fields, reducing network round-trips from one per field to one per DB.
        """
        result = {}
        for block in plc_datablocks:
            db_number = block["db_number"]
            db_name = block["properties"]["name"]
            fields = block["properties"]["data"]

            start = min(f["byte_offset"] for f in fields)
            end = max(f["byte_offset"] + self._type_sizes.get(f["type"], 1) for f in fields)
            buf = self.plc.read_db_range(db_number, start, end - start)

            db_data = {}
            for field in fields:
                parser = self._field_parsers.get(field["type"])
                if parser:
                    db_data[field["name"]] = parser(buf, field, start)
            result[db_name] = db_data
        return result