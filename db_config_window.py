from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from datablocks import calculate_offsets, plc_datablocks, save_plc_datablocks


TYPE_SIZES = {
    "Bool": 1,
    "Int": 2,
    "Time": 4,
}


class DbConfigWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowTitle("Configure DBs")
        self.setMinimumWidth(760)
        self.setMinimumHeight(520)

        self._variables: list[dict] = []
        self._selected_db_index: int | None = None
        self._selected_var_index: int | None = None

        root = QVBoxLayout(self)

        existing_group = QGroupBox("Existing Datablocks")
        existing_layout = QVBoxLayout(existing_group)
        self.db_list = QListWidget()
        self.db_list.currentRowChanged.connect(self._on_db_selected)
        existing_layout.addWidget(self.db_list)
        root.addWidget(existing_group)

        db_group = QGroupBox("Datablock")
        db_form = QFormLayout(db_group)

        self.db_number_input = QSpinBox()
        self.db_number_input.setRange(1, 65535)
        db_form.addRow("DB Number:", self.db_number_input)

        self.db_name_input = QLineEdit()
        self.db_name_input.setPlaceholderText("e.g. production_status")
        db_form.addRow("DB Name:", self.db_name_input)

        root.addWidget(db_group)

        variable_group = QGroupBox("Variables")
        variable_layout = QVBoxLayout(variable_group)

        controls = QHBoxLayout()
        self.var_name_input = QLineEdit()
        self.var_name_input.setPlaceholderText("Variable name")
        controls.addWidget(self.var_name_input, stretch=2)

        self.var_type_input = QComboBox()
        self.var_type_input.addItems(["Bool", "Int", "Time"])
        controls.addWidget(self.var_type_input, stretch=1)

        self.var_log_input = QCheckBox("Log")
        controls.addWidget(self.var_log_input)

        self.var_log_interval_input = QSpinBox()
        self.var_log_interval_input.setRange(1, 3_600_000)
        self.var_log_interval_input.setValue(1000)
        self.var_log_interval_input.setSuffix(" ms")
        self.var_log_interval_input.setEnabled(False)
        controls.addWidget(self.var_log_interval_input)
        self.var_log_input.toggled.connect(self.var_log_interval_input.setEnabled)

        self.var_byte_input = QSpinBox()
        self.var_byte_input.setRange(0, 65535)
        self.var_byte_input.setPrefix("Byte ")
        controls.addWidget(self.var_byte_input)

        self.var_bit_input = QSpinBox()
        self.var_bit_input.setRange(0, 7)
        self.var_bit_input.setPrefix("Bit ")
        controls.addWidget(self.var_bit_input)

        self.add_var_btn = QPushButton("Add Variable")
        self.add_var_btn.clicked.connect(self._on_add_variable)
        controls.addWidget(self.add_var_btn)

        self.update_var_btn = QPushButton("Update Selected")
        self.update_var_btn.clicked.connect(self._on_update_selected_variable)
        controls.addWidget(self.update_var_btn)

        variable_layout.addLayout(controls)

        self.variables_table = QTableWidget(0, 6)
        self.variables_table.setHorizontalHeaderLabels(
            ["Name", "Type", "Log", "Log Interval (ms)", "Byte Offset", "Bit Offset"]
        )
        self.variables_table.verticalHeader().setVisible(False)
        self.variables_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.variables_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.variables_table.itemSelectionChanged.connect(self._on_variable_selected)
        variable_layout.addWidget(self.variables_table)

        variable_actions = QHBoxLayout()
        self.remove_var_btn = QPushButton("Remove Selected Variable")
        self.remove_var_btn.clicked.connect(self._on_remove_selected_variable)
        variable_actions.addWidget(self.remove_var_btn)

        self.clear_vars_btn = QPushButton("Clear Variables")
        self.clear_vars_btn.clicked.connect(self._on_clear_variables)
        variable_actions.addWidget(self.clear_vars_btn)

        variable_layout.addLayout(variable_actions)

        root.addWidget(variable_group)

        footer = QHBoxLayout()
        self.offset_note = QLabel("Offsets are manually editable. Legacy entries without offsets are auto-filled on load.")
        footer.addWidget(self.offset_note)

        footer.addStretch()

        self.new_db_btn = QPushButton("New")
        self.new_db_btn.clicked.connect(self._on_new_datablock)
        footer.addWidget(self.new_db_btn)

        self.save_db_btn = QPushButton("Add Datablock")
        self.save_db_btn.clicked.connect(self._on_save_datablock)
        footer.addWidget(self.save_db_btn)

        root.addLayout(footer)

        self._refresh_db_list()
        self._on_new_datablock()

    def _refresh_db_list(self) -> None:
        self.db_list.clear()
        for block in sorted(plc_datablocks, key=lambda item: item["db_number"]):
            name = block["properties"]["name"]
            count = len(block["properties"].get("data", []))
            self.db_list.addItem(f"DB{block['db_number']} - {name} ({count} variables)")

    def _refresh_variables_table(self) -> None:
        self.variables_table.setRowCount(len(self._variables))

        for row, field in enumerate(self._variables):
            self.variables_table.setItem(row, 0, QTableWidgetItem(field["name"]))
            self.variables_table.setItem(row, 1, QTableWidgetItem(field["type"]))
            self.variables_table.setItem(row, 2, QTableWidgetItem("Yes" if field.get("log", False) else "No"))
            self.variables_table.setItem(row, 3, QTableWidgetItem(str(max(1, int(field.get("log_interval_ms", 1000))))))
            self.variables_table.setItem(row, 4, QTableWidgetItem(str(field["byte_offset"])))
            self.variables_table.setItem(row, 5, QTableWidgetItem(str(field["bit_offset"])))

    def _occupied_cells(self, variable: dict) -> set[tuple[int, int]]:
        var_type = variable["type"]
        byte_offset = int(variable["byte_offset"])
        bit_offset = int(variable["bit_offset"])

        if var_type == "Bool":
            return {(byte_offset, bit_offset)}

        size = TYPE_SIZES.get(var_type, 1)
        cells: set[tuple[int, int]] = set()
        for byte in range(byte_offset, byte_offset + size):
            for bit in range(8):
                cells.add((byte, bit))
        return cells

    def _validate_variable_layout(self, variables: list[dict]) -> str | None:
        occupied: dict[tuple[int, int], str] = {}

        for variable in variables:
            var_name = variable["name"]
            var_type = variable["type"]
            bit_offset = int(variable["bit_offset"])

            if var_type != "Bool" and bit_offset != 0:
                return f"Variable '{var_name}' of type {var_type} must use bit offset 0."

            for cell in self._occupied_cells(variable):
                if cell in occupied:
                    return (
                        f"Offset overlap between '{occupied[cell]}' and '{var_name}' "
                        f"at byte {cell[0]}, bit {cell[1]}."
                    )
                occupied[cell] = var_name

        return None

    def _find_db_index(self, db_number: int, db_name: str) -> int | None:
        for idx, block in enumerate(plc_datablocks):
            if block["db_number"] == db_number and block["properties"]["name"] == db_name:
                return idx
        return None

    def _find_db_index_by_number(self, db_number: int) -> int | None:
        for idx, block in enumerate(plc_datablocks):
            if block["db_number"] == db_number:
                return idx
        return None

    def _on_new_datablock(self) -> None:
        self._selected_db_index = None
        self._selected_var_index = None
        self.db_list.clearSelection()
        self.db_number_input.setValue(1)
        self.db_name_input.clear()
        self.var_name_input.clear()
        self.var_type_input.setCurrentIndex(0)
        self.var_log_input.setChecked(False)
        self.var_log_interval_input.setValue(1000)
        self.var_log_interval_input.setEnabled(False)
        self.var_byte_input.setValue(0)
        self.var_bit_input.setValue(0)
        self._variables.clear()
        self._refresh_variables_table()
        self.save_db_btn.setText("Add Datablock")

    def _on_db_selected(self, row: int) -> None:
        if row < 0:
            return

        item = self.db_list.item(row)
        if item is None:
            return

        text = item.text().split(" - ", 1)
        if not text or not text[0].startswith("DB"):
            return

        try:
            db_number = int(text[0][2:])
        except ValueError:
            return

        db_index = self._find_db_index_by_number(db_number)
        if db_index is None:
            return

        block = plc_datablocks[db_index]
        self._selected_db_index = db_index
        self._selected_var_index = None

        self.db_number_input.setValue(block["db_number"])
        self.db_name_input.setText(block["properties"]["name"])

        raw_fields = block["properties"].get("data", [])
        base_fields = [
            {
                "name": field.get("name", ""),
                "type": field.get("type", "Bool"),
                "log": bool(field.get("log", False)),
                "log_interval_ms": max(1, int(field.get("log_interval_ms", 1000))),
            }
            for field in raw_fields
            if field.get("name")
        ]

        has_missing_offsets = any(
            "byte_offset" not in field or "bit_offset" not in field for field in raw_fields
        )

        if has_missing_offsets:
            self._variables = calculate_offsets(base_fields)
        else:
            self._variables = [
                {
                    "name": field["name"],
                    "type": field["type"],
                    "log": bool(field.get("log", False)),
                    "log_interval_ms": max(1, int(field.get("log_interval_ms", 1000))),
                    "byte_offset": int(field.get("byte_offset", 0)),
                    "bit_offset": int(field.get("bit_offset", 0)),
                }
                for field in raw_fields
                if field.get("name")
            ]
        self._refresh_variables_table()
        self.save_db_btn.setText("Save Changes")

    def _on_variable_selected(self) -> None:
        row = self.variables_table.currentRow()
        if row < 0 or row >= len(self._variables):
            self._selected_var_index = None
            return

        self._selected_var_index = row
        variable = self._variables[row]
        self.var_name_input.setText(variable["name"])
        self.var_type_input.setCurrentText(variable["type"])
        self.var_log_input.setChecked(bool(variable.get("log", False)))
        self.var_log_interval_input.setValue(max(1, int(variable.get("log_interval_ms", 1000))))
        self.var_log_interval_input.setEnabled(bool(variable.get("log", False)))
        self.var_byte_input.setValue(int(variable.get("byte_offset", 0)))
        self.var_bit_input.setValue(int(variable.get("bit_offset", 0)))

    def _on_add_variable(self) -> None:
        var_name = self.var_name_input.text().strip()
        var_type = self.var_type_input.currentText()
        var_log = self.var_log_input.isChecked()
        var_log_interval_ms = self.var_log_interval_input.value()
        byte_offset = self.var_byte_input.value()
        bit_offset = self.var_bit_input.value()

        if not var_name:
            QMessageBox.warning(self, "Missing Name", "Please enter a variable name.")
            return

        if any(item["name"] == var_name for item in self._variables):
            QMessageBox.warning(self, "Duplicate Name", "Variable names must be unique in a DB.")
            return

        candidate = {
            "name": var_name,
            "type": var_type,
            "log": var_log,
            "log_interval_ms": var_log_interval_ms,
            "byte_offset": byte_offset,
            "bit_offset": bit_offset,
        }
        error = self._validate_variable_layout([*self._variables, candidate])
        if error is not None:
            QMessageBox.warning(self, "Invalid Offsets", error)
            return

        self._variables.append(candidate)
        self.var_name_input.clear()
        self.var_log_input.setChecked(False)
        self.var_log_interval_input.setValue(1000)
        self.var_log_interval_input.setEnabled(False)
        self._selected_var_index = None
        self._refresh_variables_table()

    def _on_update_selected_variable(self) -> None:
        if self._selected_var_index is None or self._selected_var_index >= len(self._variables):
            QMessageBox.warning(self, "No Selection", "Select a variable to update.")
            return

        var_name = self.var_name_input.text().strip()
        var_type = self.var_type_input.currentText()
        var_log = self.var_log_input.isChecked()
        var_log_interval_ms = self.var_log_interval_input.value()
        byte_offset = self.var_byte_input.value()
        bit_offset = self.var_bit_input.value()

        if not var_name:
            QMessageBox.warning(self, "Missing Name", "Please enter a variable name.")
            return

        for idx, item in enumerate(self._variables):
            if idx != self._selected_var_index and item["name"] == var_name:
                QMessageBox.warning(self, "Duplicate Name", "Variable names must be unique in a DB.")
                return

        updated = {
            "name": var_name,
            "type": var_type,
            "log": var_log,
            "log_interval_ms": var_log_interval_ms,
            "byte_offset": byte_offset,
            "bit_offset": bit_offset,
        }
        check_vars = list(self._variables)
        check_vars[self._selected_var_index] = updated

        error = self._validate_variable_layout(check_vars)
        if error is not None:
            QMessageBox.warning(self, "Invalid Offsets", error)
            return

        self._variables[self._selected_var_index] = updated
        self._refresh_variables_table()

    def _on_remove_selected_variable(self) -> None:
        row = self.variables_table.currentRow()
        if row < 0:
            return
        del self._variables[row]
        self._selected_var_index = None
        self.var_name_input.clear()
        self.var_log_input.setChecked(False)
        self.var_log_interval_input.setValue(1000)
        self.var_log_interval_input.setEnabled(False)
        self.var_byte_input.setValue(0)
        self.var_bit_input.setValue(0)
        self._refresh_variables_table()

    def _on_clear_variables(self) -> None:
        self._variables.clear()
        self._selected_var_index = None
        self.var_name_input.clear()
        self.var_log_input.setChecked(False)
        self.var_log_interval_input.setValue(1000)
        self.var_log_interval_input.setEnabled(False)
        self.var_byte_input.setValue(0)
        self.var_bit_input.setValue(0)
        self._refresh_variables_table()

    def _on_save_datablock(self) -> None:
        db_number = self.db_number_input.value()
        db_name = self.db_name_input.text().strip()

        if not db_name:
            QMessageBox.warning(self, "Missing Name", "Please enter a DB name.")
            return

        if not self._variables:
            QMessageBox.warning(self, "No Variables", "Add at least one variable.")
            return

        for idx, block in enumerate(plc_datablocks):
            if idx == self._selected_db_index:
                continue
            if block["db_number"] == db_number:
                QMessageBox.warning(self, "Duplicate DB", f"DB{db_number} already exists.")
                return
            if block["properties"]["name"] == db_name:
                QMessageBox.warning(self, "Duplicate Name", "A datablock with this name already exists.")
                return

        field_defs = [
            {
                "name": item["name"],
                "type": item["type"],
                "log": bool(item.get("log", False)),
                "log_interval_ms": max(1, int(item.get("log_interval_ms", 1000))),
                "byte_offset": int(item["byte_offset"]),
                "bit_offset": int(item["bit_offset"]),
            }
            for item in self._variables
        ]

        error = self._validate_variable_layout(field_defs)
        if error is not None:
            QMessageBox.warning(self, "Invalid Offsets", error)
            return

        db_entry = {
            "db_number": db_number,
            "properties": {
                "name": db_name,
                "data": field_defs,
            },
        }

        if self._selected_db_index is None:
            plc_datablocks.append(db_entry)
            action = "added"
        else:
            plc_datablocks[self._selected_db_index] = db_entry
            action = "updated"

        save_plc_datablocks()

        QMessageBox.information(self, "Datablock Saved", f"DB{db_number} ({db_name}) {action}.")
        self._refresh_db_list()
        selected = self._find_db_index(db_number, db_name)
        if selected is not None:
            sorted_blocks = sorted(plc_datablocks, key=lambda item: item["db_number"])
            for row, block in enumerate(sorted_blocks):
                if block["db_number"] == db_number and block["properties"]["name"] == db_name:
                    self.db_list.setCurrentRow(row)
                    break
