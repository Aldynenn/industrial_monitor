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

    _type_readers = {
        "Bool": lambda plc, db, field: plc.read_boolean(db, field["byte_offset"], field["bit_offset"]),
        "Int": lambda plc, db, field: plc.read_int(db, field["byte_offset"]),
        "Time": lambda plc, db, field: plc.read_time(db, field["byte_offset"]),
    }

    def _read_db_values(self) -> dict:
        """Read all datablock values defined in datablocks.py."""
        result = {}
        for block in plc_datablocks:
            db_number = block["db_number"]
            db_name = block["properties"]["name"]
            db_data = {}
            for field in block["properties"]["data"]:
                reader = self._type_readers.get(field["type"])
                if reader:
                    db_data[field["name"]] = reader(self.plc, db_number, field)
            result[db_name] = db_data
        return result