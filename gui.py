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
from PyQt6.QtCore import pyqtSlot, QTimer
from PyQt6.QtGui import QFont
from plc_communication import PLCWorker


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
