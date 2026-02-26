from tracemalloc import start

import snap7
import struct

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