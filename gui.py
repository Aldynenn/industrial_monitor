from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHeaderView,
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
    QTreeWidget,
    QTreeWidgetItem,
    QSystemTrayIcon,
    QMessageBox,
    QSizePolicy,
)
from PyQt6.QtCore import pyqtSlot, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPixmap
from client_auth import ClientAuthStore
from client_manager_window import ClientManagerWindow
from config import SettingsStore
from data_broker import QtDataBroker
from db_config_window import DbConfigWindow
from logging_settings_window import LoggingSettingsWindow
from plc_communication import PLCWorker
from plc_data_logger import PLCDataLogger

class MainWindow(QMainWindow):
    def __init__(self, auth_store: ClientAuthStore, settings_store: SettingsStore):
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
        self._settings_store = settings_store
        self.broker = QtDataBroker(self)
        self.broker.data_updated.connect(self._on_data)
        self._data_logger = PLCDataLogger(self.broker, self._settings_store, self)

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

        plc_settings = settings_store.get_plc()

        self.ip_input = QLineEdit(plc_settings["ip_address"])
        self.ip_input.setPlaceholderText("e.g. 192.168.0.1")
        form.addRow("PLC IP:", self.ip_input)

        self.rack_input = QSpinBox()
        self.rack_input.setRange(0, 7)
        self.rack_input.setValue(plc_settings["rack"])
        form.addRow("Rack:", self.rack_input)

        self.slot_input = QSpinBox()
        self.slot_input.setRange(0, 31)
        self.slot_input.setValue(plc_settings["slot"])
        form.addRow("Slot:", self.slot_input)

        self.auto_reconnect_input = QCheckBox("Auto-reconnect")
        form.addRow("", self.auto_reconnect_input)

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
        data_group.setCheckable(True)
        data_group.setChecked(True)
        data_group.toggled.connect(self._on_data_display_toggled)
        data_layout = QVBoxLayout()
        self.data_display = QTreeWidget()
        self.data_display.setHeaderLabels(["Name", "Value"])
        self.data_display.setColumnCount(2)
        self.data_display.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.data_display.header().setStretchLastSection(True)
        self.data_display.setRootIsDecorated(True)
        self.data_display.setAlternatingRowColors(True)
        self.data_display.setFont(QFont("Consolas", 10))
        data_layout.addWidget(self.data_display)
        data_group.setLayout(data_layout)
        layout.addWidget(data_group)
        self._data_group = data_group

        self._tree_db_items: dict[str, QTreeWidgetItem] = {}
        self._tree_field_items: dict[str, dict[str, QTreeWidgetItem]] = {}
        self._BOOL_TRUE_BG = QBrush(QColor(200, 240, 200))
        self._BOOL_FALSE_BG = QBrush(QColor(240, 200, 200))

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
        self._tree_db_items.clear()
        self._tree_field_items.clear()

        self.worker = PLCWorker(ip, rack, slot, broker=self.broker,
                                polling_interval_ms=self._settings_store.get_plc()["polling_interval_ms"],
                                auto_reconnect=self.auto_reconnect_input.isChecked())
        self.worker.error_occurred.connect(self._on_error)
        self.worker.connected.connect(self._on_connected)
        self.worker.disconnected.connect(self._on_disconnected)
        self.worker.reconnecting.connect(self._on_reconnecting)
        self.worker.finished.connect(self._on_worker_finished)
        self.auto_reconnect_input.toggled.connect(self._on_auto_reconnect_toggled)
        self.worker.start()

    def _stop_polling(self):
        self.status_label.setText("Status: Stopping...")
        self._stop_worker_if_running()

    @pyqtSlot(dict)
    def _on_data(self, data: dict):
        if not self._data_group.isChecked():
            return
        for db_name, fields in data.items():
            if db_name not in self._tree_db_items:
                db_item = QTreeWidgetItem([db_name, ""])
                font = db_item.font(0)
                font.setBold(True)
                db_item.setFont(0, font)
                self.data_display.addTopLevelItem(db_item)
                db_item.setExpanded(True)
                self._tree_db_items[db_name] = db_item
                self._tree_field_items[db_name] = {}

            db_item = self._tree_db_items[db_name]
            field_items = self._tree_field_items[db_name]

            for field_name, value in fields.items():
                text = str(value)
                if field_name not in field_items:
                    item = QTreeWidgetItem([field_name, text])
                    db_item.addChild(item)
                    field_items[field_name] = item
                else:
                    item = field_items[field_name]
                    item.setText(1, text)

                if isinstance(value, bool):
                    item.setBackground(1, self._BOOL_TRUE_BG if value else self._BOOL_FALSE_BG)

        # Remove stale DB entries
        for stale in set(self._tree_db_items) - set(data):
            idx = self.data_display.indexOfTopLevelItem(self._tree_db_items[stale])
            if idx >= 0:
                self.data_display.takeTopLevelItem(idx)
            del self._tree_db_items[stale]
            del self._tree_field_items[stale]

    @pyqtSlot(bool)
    def _on_data_display_toggled(self, checked: bool):
        self.data_display.setEnabled(checked)
        if not checked:
            self.data_display.clear()
            self._tree_db_items.clear()
            self._tree_field_items.clear()

    @pyqtSlot(str)
    def _on_error(self, msg: str):
        self.status_label.setText(f"Status: Error - {msg}")
        if not (self.worker and self.worker.auto_reconnect):
            self.start_stop_btn.setChecked(False)
            self.start_stop_btn.setText("Start")
            self._set_inputs_enabled(True)

    @pyqtSlot()
    def _on_connected(self):
        self.status_label.setText("Status: Connected - gathering data")

    @pyqtSlot()
    def _on_disconnected(self):
        self.status_label.setText("Status: Disconnected")

    @pyqtSlot(float)
    def _on_reconnecting(self, backoff: float):
        self.status_label.setText(f"Status: Reconnecting in {backoff:.0f}s...")

    @pyqtSlot()
    def _on_worker_finished(self):
        self.start_stop_btn.setChecked(False)
        self.start_stop_btn.setText("Start")
        self._set_inputs_enabled(True)
        self.auto_reconnect_input.toggled.disconnect(self._on_auto_reconnect_toggled)

    @pyqtSlot(bool)
    def _on_auto_reconnect_toggled(self, checked: bool):
        if self.worker is not None:
            self.worker.auto_reconnect = checked

    def _set_inputs_enabled(self, enabled: bool):
        self.ip_input.setEnabled(enabled)
        self.rack_input.setEnabled(enabled)
        self.slot_input.setEnabled(enabled)

    def _stop_worker_if_running(self):
        if self.worker is not None:
            self.worker.stop()
            # Process events while waiting so the GUI stays responsive
            if not self.worker.wait(500):
                QApplication.processEvents()
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
            self._logging_settings_window = LoggingSettingsWindow(self._settings_store, self)
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
