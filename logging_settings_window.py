from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logging_config import LoggingSettingsStore


class LoggingSettingsWindow(QWidget):
    """Window for configuring global PLC logging settings."""

    def __init__(self, settings_store: LoggingSettingsStore, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowTitle("Logging Settings")
        self.setMinimumWidth(560)

        self._settings_store = settings_store

        root = QVBoxLayout(self)

        group = QGroupBox("Global Logging")
        form = QFormLayout(group)

        self.enabled_input = QCheckBox("Enable logging")
        form.addRow("Status:", self.enabled_input)

        path_row = QHBoxLayout()
        self.output_file_input = QLineEdit()
        self.output_file_input.setPlaceholderText("Path to log file")
        path_row.addWidget(self.output_file_input)

        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self._on_browse)
        path_row.addWidget(self.browse_btn)
        form.addRow("Output file:", path_row)

        self.include_header_input = QCheckBox("Write header for new files")
        form.addRow("Header:", self.include_header_input)

        root.addWidget(group)

        actions = QHBoxLayout()
        actions.addStretch()

        self.reload_btn = QPushButton("Reload")
        self.reload_btn.clicked.connect(self._load_from_store)
        actions.addWidget(self.reload_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._on_save)
        actions.addWidget(self.save_btn)

        root.addLayout(actions)

        self._load_from_store()

    def _load_from_store(self) -> None:
        self._settings_store.load()
        settings = self._settings_store.get()
        self.enabled_input.setChecked(bool(settings.get("enabled", False)))
        self.output_file_input.setText(str(settings.get("output_file", "plc_logs.log")))
        self.include_header_input.setChecked(bool(settings.get("include_header", True)))

    def _on_browse(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Select Log File",
            self.output_file_input.text().strip() or "plc_logs.log",
            "Log files (*.log);;All files (*.*)",
        )
        if selected:
            self.output_file_input.setText(selected)

    def _on_save(self) -> None:
        try:
            self._settings_store.update(
                enabled=self.enabled_input.isChecked(),
                output_file=self.output_file_input.text(),
                include_header=self.include_header_input.isChecked(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Settings", str(exc))
            return

        QMessageBox.information(self, "Saved", "Logging settings updated.")
