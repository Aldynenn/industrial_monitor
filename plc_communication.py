from tracemalloc import start

import snap7

class PLCCommunication:
    connection_error = False

    def __init__(self, ip_address, rack, slot):
        self.plc = snap7.client.Client()
        try:
            self.plc.connect(ip_address, rack, slot)
            self.connection_error = self.plc.get_connected()
        except Exception as e:
            print(f"Error connecting to PLC: {e}")
            self.connection_error = True

    def disconnect(self):
        self.plc.disconnect()

    def read_boolean(self, db_number, start, size):
        data = self.plc.db_read(db_number, start, size)
        return snap7.util.get_bool(data, 0, 0)
    
    def write_boolean(self, db_number, start_offset, bit_offset, value):
        reading = self.plc.db_read(db_number, start_offset, 1)
        snap7.util.set_bool(reading, 0, bit_offset, value)
        self.plc.db_write(db_number, start_offset, reading)

    def read_integer(self, db_number, start_offset):
        data = self.plc.db_read(db_number, start_offset, 2)
        return snap7.util.get_int(data, 0)
    
    def write_integer(self, db_number, start_offset, bit_offset, value):
        data = bytearray(2)
        snap7.util.set_int(data, 0, value)
        self.plc.db_write(db_number, start_offset, data)

    def read_real(self, db_number, start_offset):
        data = self.plc.db_read(db_number, start_offset, 4)
        return snap7.util.get_real(data, 0)
    
    def write_real(self, db_number, start_offset, bit_offset, value):
        data = bytearray(4)
        snap7.util.set_real(data, 0, value)
        self.plc.db_write(db_number, start, data)

    def read_string(self, db_number, start, size):
        data = self.plc.db_read(db_number, start, size)
        return snap7.util.get_string(data, 0, size)
    
    def write_string(self, db_number, start, value, size):
        data = bytearray(size)
        snap7.util.set_string(data, 0, value)
        self.plc.db_write(db_number, start, data)