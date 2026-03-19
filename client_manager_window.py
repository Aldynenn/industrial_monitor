from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from client_auth import ClientAuthStore


class ClientManagerWindow(QWidget):
    """Separate window used to manage WebSocket client credentials."""

    def __init__(self, auth_store: ClientAuthStore, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowTitle("Manage WebSocket Clients")
        self.setMinimumWidth(820)
        self.setMinimumHeight(500)

        self._auth_store = auth_store
        self._selected_client_id: int | None = None
        self._selected_is_active = True
        self._selected_role = "user"

        root = QVBoxLayout(self)

        help_label = QLabel("Clients authenticate to receive PLC data over WebSocket.")
        root.addWidget(help_label)

        form_group = QGroupBox("Client Credentials")
        form_layout = QFormLayout(form_group)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        form_layout.addRow("Username:", self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Password (min 4 chars)")
        form_layout.addRow("Password:", self.password_input)

        self.role_input = QComboBox()
        self.role_input.addItems(["user", "admin"])
        form_layout.addRow("Role:", self.role_input)

        add_row = QHBoxLayout()
        self.add_btn = QPushButton("Add Client")
        self.add_btn.clicked.connect(self._on_add_client)
        add_row.addWidget(self.add_btn)

        self.update_password_btn = QPushButton("Update Selected Password")
        self.update_password_btn.clicked.connect(self._on_update_password)
        add_row.addWidget(self.update_password_btn)

        form_layout.addRow(add_row)
        root.addWidget(form_group)

        self.clients_table = QTableWidget(0, 6)
        self.clients_table.setHorizontalHeaderLabels(["ID", "Username", "Role", "Active", "Created", "Last Auth"])
        self.clients_table.verticalHeader().setVisible(False)
        self.clients_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.clients_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.clients_table.itemSelectionChanged.connect(self._on_selected_client_changed)
        root.addWidget(self.clients_table)

        actions = QHBoxLayout()
        self.toggle_active_btn = QPushButton("Disable Selected")
        self.toggle_active_btn.clicked.connect(self._on_toggle_active)
        actions.addWidget(self.toggle_active_btn)

        self.toggle_role_btn = QPushButton("Set Selected As Admin")
        self.toggle_role_btn.clicked.connect(self._on_toggle_role)
        actions.addWidget(self.toggle_role_btn)

        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.clicked.connect(self._on_delete_selected)
        actions.addWidget(self.delete_btn)

        actions.addStretch()

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._reload_clients)
        actions.addWidget(self.refresh_btn)

        root.addLayout(actions)

        self._reload_clients()

    def _reload_clients(self) -> None:
        clients = self._auth_store.list_clients()
        self.clients_table.setRowCount(len(clients))

        for row, client in enumerate(clients):
            self.clients_table.setItem(row, 0, QTableWidgetItem(str(client["id"])))
            self.clients_table.setItem(row, 1, QTableWidgetItem(client["username"]))
            self.clients_table.setItem(row, 2, QTableWidgetItem(client["role"]))
            self.clients_table.setItem(row, 3, QTableWidgetItem("Yes" if client["is_active"] else "No"))
            self.clients_table.setItem(row, 4, QTableWidgetItem(client["created_at"]))
            self.clients_table.setItem(row, 5, QTableWidgetItem(client["last_auth_at"] or "-"))

        self._selected_client_id = None
        self._selected_is_active = True
        self._selected_role = "user"
        self.toggle_active_btn.setText("Disable Selected")
        self.toggle_role_btn.setText("Set Selected As Admin")

    def _on_selected_client_changed(self) -> None:
        row = self.clients_table.currentRow()
        if row < 0:
            self._selected_client_id = None
            self._selected_is_active = True
            self._selected_role = "user"
            self.toggle_active_btn.setText("Disable Selected")
            self.toggle_role_btn.setText("Set Selected As Admin")
            return

        id_item = self.clients_table.item(row, 0)
        role_item = self.clients_table.item(row, 2)
        active_item = self.clients_table.item(row, 3)
        if id_item is None or role_item is None or active_item is None:
            return

        self._selected_client_id = int(id_item.text())
        self._selected_role = role_item.text().strip().lower()
        self._selected_is_active = active_item.text().strip().lower() == "yes"
        self.toggle_active_btn.setText("Disable Selected" if self._selected_is_active else "Enable Selected")
        self.toggle_role_btn.setText(
            "Set Selected As User" if self._selected_role == "admin" else "Set Selected As Admin"
        )

    def _on_add_client(self) -> None:
        username = self.username_input.text().strip()
        password = self.password_input.text()
        role = self.role_input.currentText()

        try:
            self._auth_store.add_client(username, password, role=role)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot Add Client", str(exc))
            return

        self.username_input.clear()
        self.password_input.clear()
        self._reload_clients()

    def _on_update_password(self) -> None:
        if self._selected_client_id is None:
            QMessageBox.warning(self, "No Selection", "Select a client first.")
            return

        password = self.password_input.text()
        try:
            self._auth_store.update_password(self._selected_client_id, password)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot Update Password", str(exc))
            return

        self.password_input.clear()
        self._reload_clients()

    def _on_toggle_active(self) -> None:
        if self._selected_client_id is None:
            QMessageBox.warning(self, "No Selection", "Select a client first.")
            return

        self._auth_store.set_active(self._selected_client_id, not self._selected_is_active)
        self._reload_clients()

    def _on_toggle_role(self) -> None:
        if self._selected_client_id is None:
            QMessageBox.warning(self, "No Selection", "Select a client first.")
            return

        next_role = "user" if self._selected_role == "admin" else "admin"
        self._auth_store.set_role(self._selected_client_id, next_role)
        self._reload_clients()

    def _on_delete_selected(self) -> None:
        if self._selected_client_id is None:
            QMessageBox.warning(self, "No Selection", "Select a client first.")
            return

        response = QMessageBox.question(
            self,
            "Delete Client",
            "Delete selected client? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return

        self._auth_store.delete_client(self._selected_client_id)
        self._reload_clients()
