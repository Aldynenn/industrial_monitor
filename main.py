from config import IP_ADDRESS, RACK_NUMBER, SLOT_NUMBER
from plc_communication import PLCCommunication
import plc_communication



def main():
    plc_comm = PLCCommunication(IP_ADDRESS, RACK_NUMBER, SLOT_NUMBER)
    if not plc_comm.connection_error:
        print("PLC Communication initialized successfully.")
        mode = input("Set mode: ")
        plc_comm.write_boolean(1, 0, 4, int(mode))
        plc_comm.disconnect()

if __name__ == "__main__":
    main()
