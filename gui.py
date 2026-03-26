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
    QSystemTrayIcon,
    QMessageBox,
    QSizePolicy,
)
from PyQt6.QtCore import pyqtSlot, Qt
from PyQt6.QtGui import QFont, QPixmap
from client_auth import ClientAuthStore
from client_manager_window import ClientManagerWindow
import config
from data_broker import QtDataBroker
from db_config_window import DbConfigWindow
from logging_config import LoggingSettingsStore
from logging_settings_window import LoggingSettingsWindow
from plc_communication import PLCWorker
from plc_data_logger import PLCDataLogger

class MainWindow(QMainWindow):
    def __init__(self, auth_store: ClientAuthStore, logging_settings_store: LoggingSettingsStore):
        super().__init__()
        self.setWindowTitle("Industrial Monitor")
        self.setMinimumWidth(480)

        self._force_quit = False
        self._tray = None
        self._db_config_window = None
        self._client_manager_window = None
        self._logging_settings_window = None
        self.worker = None
        self._auth_store = auth_store
        self._logging_settings_store = logging_settings_store
        self.broker = QtDataBroker(self)
        self.broker.data_updated.connect(self._on_data)
        self._data_logger = PLCDataLogger(self.broker, self._logging_settings_store, self)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # -------------------- Logo --------------------
        import os
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gamf_logo.jpg")
        self._logo_pixmap = QPixmap(logo_path)
        self._logo_label = QLabel()
        self._logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo_label.setMaximumWidth(600)
        if not self._logo_pixmap.isNull():
            self._logo_label.setMinimumHeight(1)
            sp = self._logo_label.sizePolicy()
            sp.setVerticalPolicy(QSizePolicy.Policy.Fixed)
            self._logo_label.setSizePolicy(sp)
        layout.addWidget(self._logo_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        # -------------------- Connection settings --------------------
        conn_group = QGroupBox("PLC Connection")
        form = QFormLayout()

        self.ip_input = QLineEdit(config.DEFAULT_IP_ADDRESS)
        self.ip_input.setPlaceholderText("e.g. 192.168.0.1")
        form.addRow("PLC IP:", self.ip_input)

        self.rack_input = QSpinBox()
        self.rack_input.setRange(0, 7)
        self.rack_input.setValue(config.DEFAULT_RACK_NUMBER)
        form.addRow("Rack:", self.rack_input)

        self.slot_input = QSpinBox()
        self.slot_input.setRange(0, 31)
        self.slot_input.setValue(config.DEFAULT_SLOT_NUMBER)
        form.addRow("Slot:", self.slot_input)

        conn_group.setLayout(form)
        layout.addWidget(conn_group)

        # -------------------- Start / Stop button --------------------
        btn_layout = QHBoxLayout()
        self.start_stop_btn = QPushButton("Start")
        self.start_stop_btn.setCheckable(True)
        self.start_stop_btn.setMinimumHeight(36)
        self.start_stop_btn.clicked.connect(self._on_start_stop)
        btn_layout.addWidget(self.start_stop_btn)

        self.configure_dbs_btn = QPushButton("Configure DBs")
        self.configure_dbs_btn.setMinimumHeight(36)
        self.configure_dbs_btn.clicked.connect(self._open_db_config_window)
        btn_layout.addWidget(self.configure_dbs_btn)

        self.manage_clients_btn = QPushButton("Manage Clients")
        self.manage_clients_btn.setMinimumHeight(36)
        self.manage_clients_btn.clicked.connect(self._open_client_manager_window)
        btn_layout.addWidget(self.manage_clients_btn)

        self.logging_settings_btn = QPushButton("Logging Settings")
        self.logging_settings_btn.setMinimumHeight(36)
        self.logging_settings_btn.clicked.connect(self._open_logging_settings_window)
        btn_layout.addWidget(self.logging_settings_btn)

        layout.addLayout(btn_layout)

        # -------------------- Status label --------------------
        self.status_label = QLabel("Status: Idle")
        layout.addWidget(self.status_label)

        # -------------------- Data display --------------------
        data_group = QGroupBox("PLC Data")
        data_layout = QVBoxLayout()
        self.data_display = QTextEdit()
        self.data_display.setReadOnly(True)
        self.data_display.setFont(QFont("Consolas", 10))
        data_layout.addWidget(self.data_display)
        data_group.setLayout(data_layout)
        layout.addWidget(data_group)

    # -------------------- Slots --------------------

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

        self.worker = PLCWorker(ip, rack, slot, broker=self.broker)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.connected.connect(self._on_connected)
        self.worker.disconnected.connect(self._on_disconnected)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _stop_polling(self):
        self.status_label.setText("Status: Stopping...")
        self._stop_worker_if_running()

    @pyqtSlot(dict)
    def _on_data(self, data: dict):
        lines = [f"{k}: {v}" for k, v in data.items()]
        self.data_display.setPlainText("\n".join(lines))

    @pyqtSlot(str)
    def _on_error(self, msg: str):
        self.status_label.setText(f"Status: Error - {msg}")
        self.start_stop_btn.setChecked(False)
        self.start_stop_btn.setText("Start")
        self._set_inputs_enabled(True)

    @pyqtSlot()
    def _on_connected(self):
        self.status_label.setText("Status: Connected - gathering data")

    @pyqtSlot()
    def _on_disconnected(self):
        self.status_label.setText("Status: Disconnected")

    @pyqtSlot()
    def _on_worker_finished(self):
        self.start_stop_btn.setChecked(False)
        self.start_stop_btn.setText("Start")
        self._set_inputs_enabled(True)

    def _set_inputs_enabled(self, enabled: bool):
        self.ip_input.setEnabled(enabled)
        self.rack_input.setEnabled(enabled)
        self.slot_input.setEnabled(enabled)

    def _stop_worker_if_running(self):
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait(3000)

    def _open_db_config_window(self):
        if self._db_config_window is None:
            self._db_config_window = DbConfigWindow(self)
        self._db_config_window.show()
        self._db_config_window.raise_()
        self._db_config_window.activateWindow()

    def _open_client_manager_window(self):
        if self._client_manager_window is None:
            self._client_manager_window = ClientManagerWindow(self._auth_store, self)
        self._client_manager_window.show()
        self._client_manager_window.raise_()
        self._client_manager_window.activateWindow()

    def _open_logging_settings_window(self):
        if self._logging_settings_window is None:
            self._logging_settings_window = LoggingSettingsWindow(self._logging_settings_store, self)
        self._logging_settings_window.show()
        self._logging_settings_window.raise_()
        self._logging_settings_window.activateWindow()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._logo_pixmap.isNull():
            w = min(self._logo_label.width(), 600)
            scaled = self._logo_pixmap.scaledToWidth(w, Qt.TransformationMode.SmoothTransformation)
            self._logo_label.setPixmap(scaled)
            self._logo_label.setFixedHeight(scaled.height())

    def closeEvent(self, event):
        if not self._force_quit and self._tray and QSystemTrayIcon.isSystemTrayAvailable():
            msg = QMessageBox(self)
            msg.setWindowTitle("Industrial Monitor")
            msg.setText("What would you like to do?")
            minimize_btn = msg.addButton("Minimize to tray", QMessageBox.ButtonRole.AcceptRole)
            quit_btn = msg.addButton("Quit", QMessageBox.ButtonRole.DestructiveRole)
            msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            msg.exec()

            clicked = msg.clickedButton()
            if clicked is minimize_btn:
                event.ignore()
                self.hide()
                self._tray.showMessage(
                    "Industrial Monitor",
                    "Running in the background. Right-click the tray icon to quit.",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                )
            elif clicked is quit_btn:
                self._stop_worker_if_running()
                event.accept()
                QApplication.quit()
            else:
                event.ignore()
        else:
            # Actually quit: stop worker, clean up
            self._stop_worker_if_running()
            event.accept()
