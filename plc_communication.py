import snap7
from PyQt6.QtCore import QThread, pyqtSignal

import config

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

    def _read_db_values(self) -> dict:
        """Read DB1 values from the PLC."""
        plc = self.plc
        return {
            "el01": plc.read_boolean(1, 0, 0),
            "el02": plc.read_boolean(1, 0, 1),
            "el03": plc.read_boolean(1, 0, 2),
            "el04": plc.read_boolean(1, 0, 3),
            "el05": plc.read_boolean(1, 0, 4),
            "el06": plc.read_boolean(1, 0, 5),
            "el07": plc.read_boolean(1, 0, 6),
            "el08": plc.read_boolean(1, 0, 7),
            "eoff_signal": plc.read_boolean(1, 1, 0),
            "etimer_duration": plc.read_time(1, 2),
            "btn_green": plc.read_boolean(1, 6, 0),
        }