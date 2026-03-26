import ctypes
import logging
import math
import struct
import threading
import time

import snap7
from snap7.type import Area, Parameter, S7DataItem, WordLen

from config import DEFAULTS
from datablocks import TYPE_SIZES, plc_datablocks

_DEFAULT_POLLING_MS = DEFAULTS["plc"]["polling_interval_ms"]

_RECONNECT_BASE_S = 1
_RECONNECT_MAX_S = 60
_MAX_MULTI_ITEMS = 20  # S7 protocol limit per single PDU

logger = logging.getLogger(__name__)


def _parse_field_value(buf: bytes, field: dict, base: int):
    offset = int(field["byte_offset"]) - base
    field_type = field.get("type")
    size = TYPE_SIZES.get(field_type)
    if size is None:
        return None

    # Guard against truncated / corrupted buffer.
    if offset < 0 or offset + size > len(buf):
        raise ValueError(
            f"Buffer overrun for field '{field.get('name')}': "
            f"offset={offset}, size={size}, buf_len={len(buf)}"
        )

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
        value = struct.unpack(">f", buf[offset: offset + 4])[0]
        if not math.isfinite(value):
            raise ValueError(
                f"Non-finite Real for field '{field.get('name')}': {value}"
            )
        return value
    if field_type == "LReal":
        value = struct.unpack(">d", buf[offset: offset + 8])[0]
        if not math.isfinite(value):
            raise ValueError(
                f"Non-finite LReal for field '{field.get('name')}': {value}"
            )
        return value
    if field_type == "Time":
        # Siemens TIME stores milliseconds in a signed 32-bit integer.
        return int.from_bytes(buf[offset: offset + 4], byteorder="big", signed=True)

    return None


class PLCCommunication:
    is_connected = False

    def __init__(self, ip_address, rack, slot):
        self.plc = snap7.client.Client()
        try:
            self.plc.set_param(Parameter.PDURequest, 960)
            self.plc.connect(ip_address, rack, slot)
            self.is_connected = self.plc.get_connected()
            logger.info("Connected to PLC: %s (PDU: %d)",
                        self.is_connected, self.plc.get_pdu_length())
        except Exception as e:
            logger.error("Error connecting to PLC: %s", e)
            self.is_connected = False

    def disconnect(self):
        self.plc.disconnect()

    def read_db_range(self, db_number, start, size):
        return self.plc.db_read(db_number, start, size)

    def read_all_dbs(self) -> dict:
        """Read all datablock values using batched multi-var reads.

        Packs up to 20 DB read requests into a single S7 PDU via
        ``read_multi_vars``, drastically reducing network round-trips
        compared to one ``db_read`` call per datablock.
        """
        # Build the request list: one item per datablock.
        requests: list[tuple[dict, int, int]] = []  # (block, start, size)
        for block in plc_datablocks:
            fields = block["properties"]["data"]
            start = min(f["byte_offset"] for f in fields)
            end = max(f["byte_offset"] + TYPE_SIZES.get(f["type"], 1) for f in fields)
            requests.append((block, start, end - start))

        # Process in batches of _MAX_MULTI_ITEMS (S7 protocol limit).
        result = {}
        for batch_start in range(0, len(requests), _MAX_MULTI_ITEMS):
            batch = requests[batch_start:batch_start + _MAX_MULTI_ITEMS]
            items = (S7DataItem * len(batch))()
            buffers = []

            for i, (block, start, size) in enumerate(batch):
                buf = ctypes.create_string_buffer(size)
                buffers.append(buf)
                items[i].Area = Area.DB.value
                items[i].WordLen = WordLen.Byte.value
                items[i].DBNumber = block["db_number"]
                items[i].Start = start
                items[i].Amount = size
                items[i].pData = ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint8))

            code, items = self.plc.read_multi_vars(items)

            for i, (block, start, _size) in enumerate(batch):
                db_name = block["properties"]["name"]
                fields = block["properties"]["data"]

                if items[i].Result != 0:
                    logger.warning("Failed to read DB %s (DB%d), result=%d",
                                   db_name, block["db_number"], items[i].Result)
                    continue

                raw = bytes(buffers[i])
                db_data = {}
                for field in fields:
                    try:
                        value = _parse_field_value(raw, field, start)
                    except Exception:
                        logger.warning("Bad value in DB %s field '%s', skipping",
                                       db_name, field.get("name"), exc_info=True)
                        continue
                    if value is not None:
                        db_data[field["name"]] = value
                result[db_name] = db_data

        return result


class HeadlessPLCWorker(threading.Thread):
    """Polling thread that reads PLC data without any Qt dependency."""

    def __init__(self, ip: str, rack: int, slot: int, broker=None,
                 on_connected=None, on_disconnected=None, on_error=None,
                 polling_interval_ms: int = _DEFAULT_POLLING_MS,
                 auto_reconnect: bool = False):
        super().__init__(daemon=True)
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self._broker = broker
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected
        self._on_error = on_error
        self._polling_interval_ms = polling_interval_ms
        self.auto_reconnect = auto_reconnect
        self._stop_event = threading.Event()
        self.plc: PLCCommunication | None = None

    def run(self):
        backoff = _RECONNECT_BASE_S
        while not self._stop_event.is_set():
            # --- connect ---
            try:
                self.plc = PLCCommunication(self.ip, self.rack, self.slot)
                if not self.plc.is_connected:
                    raise ConnectionError("Failed to connect to PLC.")
            except Exception as e:
                if self._on_error:
                    self._on_error(str(e))
                if not self.auto_reconnect:
                    break
                logger.info("Reconnecting in %ss...", backoff)
                if self._stop_event.wait(backoff):
                    break
                backoff = min(backoff * 2, _RECONNECT_MAX_S)
                continue

            backoff = _RECONNECT_BASE_S
            if self._on_connected:
                self._on_connected()

            # --- poll ---
            interval_s = self._polling_interval_ms / 1000
            while not self._stop_event.is_set():
                t0 = time.monotonic()
                try:
                    data = self.plc.read_all_dbs()
                    if self._broker:
                        self._broker.update(data)
                except Exception as e:
                    if self._on_error:
                        self._on_error(str(e))
                    break
                remaining = interval_s - (time.monotonic() - t0)
                if remaining > 0:
                    self._stop_event.wait(remaining)

            # --- cleanup ---
            try:
                if self.plc:
                    self.plc.disconnect()
            except Exception:
                pass

            if not self.auto_reconnect or self._stop_event.is_set():
                break
            logger.info("Reconnecting in %ss...", backoff)
            if self._stop_event.wait(backoff):
                break
            backoff = min(backoff * 2, _RECONNECT_MAX_S)

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
        reconnecting = pyqtSignal(float)  # emits backoff seconds

        def __init__(self, ip: str, rack: int, slot: int, broker=None,
                     polling_interval_ms: int = _DEFAULT_POLLING_MS,
                     auto_reconnect: bool = False):
            super().__init__()
            self.ip = ip
            self.rack = rack
            self.slot = slot
            self._running = False
            self._polling_interval_ms = polling_interval_ms
            self.auto_reconnect = auto_reconnect
            self.plc: PLCCommunication | None = None
            self._broker = broker

        def run(self):
            backoff = _RECONNECT_BASE_S
            while True:
                # --- connect ---
                try:
                    self.plc = PLCCommunication(self.ip, self.rack, self.slot)
                    if not self.plc.is_connected:
                        raise ConnectionError("Failed to connect to PLC.")
                except Exception as e:
                    self.error_occurred.emit(str(e))
                    if not self.auto_reconnect:
                        break
                    self.reconnecting.emit(backoff)
                    self.msleep(int(backoff * 1000))
                    if not self._running and not self.auto_reconnect:
                        break
                    if not self._running:
                        break
                    backoff = min(backoff * 2, _RECONNECT_MAX_S)
                    continue

                backoff = _RECONNECT_BASE_S
                self._running = True
                self.connected.emit()

                # --- poll ---
                interval_s = self._polling_interval_ms / 1000
                while self._running:
                    t0 = time.monotonic()
                    try:
                        data = self.plc.read_all_dbs()
                        if self._broker:
                            self._broker.update(data)
                    except Exception as e:
                        self.error_occurred.emit(str(e))
                        break
                    remaining_ms = int((interval_s - (time.monotonic() - t0)) * 1000)
                    if remaining_ms > 0:
                        self.msleep(remaining_ms)

                # --- cleanup ---
                try:
                    if self.plc:
                        self.plc.disconnect()
                except Exception:
                    pass

                if not self.auto_reconnect or not self._running:
                    break
                self.reconnecting.emit(backoff)
                self.msleep(int(backoff * 1000))
                if not self._running:
                    break
                backoff = min(backoff * 2, _RECONNECT_MAX_S)

            self.disconnected.emit()

        def stop(self):
            self.auto_reconnect = False
            self._running = False

except ImportError:
    pass