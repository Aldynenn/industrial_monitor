import logging
import struct
import threading
import time

import snap7

import config
from datablocks import TYPE_SIZES, plc_datablocks

logger = logging.getLogger(__name__)


def _parse_field_value(buf: bytes, field: dict, base: int):
    offset = int(field["byte_offset"]) - base
    field_type = field.get("type")

    if field_type == "Bool":
        return snap7.util.get_bool(buf, offset, int(field.get("bit_offset", 0)))
    if field_type == "Byte":
        return int.from_bytes(buf[offset: offset + 1], byteorder="big", signed=False)
    if field_type == "SInt":
        return int.from_bytes(buf[offset: offset + 1], byteorder="big", signed=True)
    if field_type == "USInt":
        return int.from_bytes(buf[offset: offset + 1], byteorder="big", signed=False)
    if field_type == "Word":
        return int.from_bytes(buf[offset: offset + 2], byteorder="big", signed=False)
    if field_type == "Int":
        return int.from_bytes(buf[offset: offset + 2], byteorder="big", signed=True)
    if field_type == "UInt":
        return int.from_bytes(buf[offset: offset + 2], byteorder="big", signed=False)
    if field_type == "DWord":
        return int.from_bytes(buf[offset: offset + 4], byteorder="big", signed=False)
    if field_type == "DInt":
        return int.from_bytes(buf[offset: offset + 4], byteorder="big", signed=True)
    if field_type == "UDInt":
        return int.from_bytes(buf[offset: offset + 4], byteorder="big", signed=False)
    if field_type == "Real":
        return struct.unpack(">f", buf[offset: offset + 4])[0]
    if field_type == "LReal":
        return struct.unpack(">d", buf[offset: offset + 8])[0]
    if field_type == "Time":
        # Siemens TIME stores milliseconds in a signed 32-bit integer.
        return int.from_bytes(buf[offset: offset + 4], byteorder="big", signed=True)

    return None


class PLCCommunication:
    is_connected = False

    def __init__(self, ip_address, rack, slot):
        self.plc = snap7.client.Client()
        try:
            self.plc.connect(ip_address, rack, slot)
            self.is_connected = self.plc.get_connected()
            logger.info("Connected to PLC: %s", self.is_connected)
        except Exception as e:
            logger.error("Error connecting to PLC: %s", e)
            self.is_connected = False

    def disconnect(self):
        self.plc.disconnect()

    def read_db_range(self, db_number, start, size):
        return self.plc.db_read(db_number, start, size)

    def read_all_dbs(self) -> dict:
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
            end = max(f["byte_offset"] + TYPE_SIZES.get(f["type"], 1) for f in fields)
            buf = self.read_db_range(db_number, start, end - start)

            db_data = {}
            for field in fields:
                value = _parse_field_value(buf, field, start)
                if value is not None:
                    db_data[field["name"]] = value
            result[db_name] = db_data
        return result


class HeadlessPLCWorker(threading.Thread):
    """Polling thread that reads PLC data without any Qt dependency."""

    def __init__(self, ip: str, rack: int, slot: int, broker=None,
                 on_connected=None, on_disconnected=None, on_error=None):
        super().__init__(daemon=True)
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self._broker = broker
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected
        self._on_error = on_error
        self._stop_event = threading.Event()
        self.plc: PLCCommunication | None = None

    def run(self):
        try:
            self.plc = PLCCommunication(self.ip, self.rack, self.slot)
            if not self.plc.is_connected:
                if self._on_error:
                    self._on_error("Failed to connect to PLC.")
                return
            if self._on_connected:
                self._on_connected()
        except Exception as e:
            if self._on_error:
                self._on_error(str(e))
            return

        while not self._stop_event.is_set():
            try:
                data = self.plc.read_all_dbs()
                if self._broker:
                    self._broker.update(data)
            except Exception as e:
                if self._on_error:
                    self._on_error(str(e))
                break
            self._stop_event.wait(config.POLLING_INTERVAL_MS / 1000)

        try:
            if self.plc:
                self.plc.disconnect()
        except Exception:
            pass
        if self._on_disconnected:
            self._on_disconnected()

    def stop(self):
        self._stop_event.set()


# ---------------------------------------------------------------------------
# Qt-based worker (only available when PyQt6 is installed)
# ---------------------------------------------------------------------------

try:
    from PyQt6.QtCore import QThread, pyqtSignal

    class PLCWorker(QThread):
        """Worker thread that polls PLC data periodically (Qt version)."""

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
                if not self.plc.is_connected:
                    self.error_occurred.emit("Failed to connect to PLC.")
                    return
                self.connected.emit()
            except Exception as e:
                self.error_occurred.emit(str(e))
                return

            self._running = True
            while self._running:
                try:
                    data = self.plc.read_all_dbs()
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

except ImportError:
    pass