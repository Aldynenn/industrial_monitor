import sys
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QPushButton,
    QLabel,
    QGroupBox,
    QTextEdit,
)
from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtGui import QFont
from plc_communication import PLCCommunication


class PLCWorker(QThread):
    """Worker thread that polls PLC data periodically."""

    data_received = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    connected = pyqtSignal()
    disconnected = pyqtSignal()

    def __init__(self, ip: str, rack: int, slot: int):
        super().__init__()
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self._running = False
        self.plc: PLCCommunication | None = None

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
                self.data_received.emit(data)
            except Exception as e:
                self.error_occurred.emit(str(e))
                self._running = False
                break
            self.msleep(200)  # poll every 200 ms

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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Industrial Monitor")
        self.setMinimumWidth(480)
        self.worker: PLCWorker | None = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # ── Connection settings ──────────────────────────────
        conn_group = QGroupBox("PLC Connection")
        form = QFormLayout()

        self.ip_input = QLineEdit("192.168.0.27")
        self.ip_input.setPlaceholderText("e.g. 192.168.0.27")
        form.addRow("PLC IP:", self.ip_input)

        self.rack_input = QSpinBox()
        self.rack_input.setRange(0, 7)
        self.rack_input.setValue(0)
        form.addRow("Rack:", self.rack_input)

        self.slot_input = QSpinBox()
        self.slot_input.setRange(0, 31)
        self.slot_input.setValue(1)
        form.addRow("Slot:", self.slot_input)

        conn_group.setLayout(form)
        layout.addWidget(conn_group)

        # ── Start / Stop button ──────────────────────────────
        btn_layout = QHBoxLayout()
        self.start_stop_btn = QPushButton("Start")
        self.start_stop_btn.setCheckable(True)
        self.start_stop_btn.setMinimumHeight(36)
        self.start_stop_btn.clicked.connect(self._on_start_stop)
        btn_layout.addWidget(self.start_stop_btn)
        layout.addLayout(btn_layout)

        # ── Status label ─────────────────────────────────────
        self.status_label = QLabel("Status: Idle")
        layout.addWidget(self.status_label)

        # ── Data display ─────────────────────────────────────
        data_group = QGroupBox("PLC Data")
        data_layout = QVBoxLayout()
        self.data_display = QTextEdit()
        self.data_display.setReadOnly(True)
        self.data_display.setFont(QFont("Consolas", 10))
        data_layout.addWidget(self.data_display)
        data_group.setLayout(data_layout)
        layout.addWidget(data_group)

    # ── Slots ────────────────────────────────────────────────

    def _on_start_stop(self, checked: bool):
        if checked:
            self._start_polling()
        else:
            self._stop_polling()

    def _start_polling(self):
        ip = self.ip_input.text().strip()
        rack = self.rack_input.value()
        slot = self.slot_input.value()

        if not ip:
            self.status_label.setText("Status: Please enter a PLC IP address.")
            self.start_stop_btn.setChecked(False)
            return

        self._set_inputs_enabled(False)
        self.start_stop_btn.setText("Stop")
        self.status_label.setText("Status: Connecting...")
        self.data_display.clear()

        self.worker = PLCWorker(ip, rack, slot)
        self.worker.data_received.connect(self._on_data)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.connected.connect(self._on_connected)
        self.worker.disconnected.connect(self._on_disconnected)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _stop_polling(self):
        self.status_label.setText("Status: Stopping...")
        if self.worker:
            self.worker.stop()

    @pyqtSlot(dict)
    def _on_data(self, data: dict):
        lines = [f"{k}: {v}" for k, v in data.items()]
        self.data_display.setPlainText("\n".join(lines))

    @pyqtSlot(str)
    def _on_error(self, msg: str):
        self.status_label.setText(f"Status: Error – {msg}")
        self.start_stop_btn.setChecked(False)
        self.start_stop_btn.setText("Start")
        self._set_inputs_enabled(True)

    @pyqtSlot()
    def _on_connected(self):
        self.status_label.setText("Status: Connected – gathering data")

    @pyqtSlot()
    def _on_disconnected(self):
        self.status_label.setText("Status: Disconnected")

    @pyqtSlot()
    def _on_worker_finished(self):
        self.start_stop_btn.setChecked(False)
        self.start_stop_btn.setText("Start")
        self._set_inputs_enabled(True)
        self.worker = None

    def _set_inputs_enabled(self, enabled: bool):
        self.ip_input.setEnabled(enabled)
        self.rack_input.setEnabled(enabled)
        self.slot_input.setEnabled(enabled)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        event.accept()


def launch():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
