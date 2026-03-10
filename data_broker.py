from PyQt6.QtCore import QObject, pyqtSignal


class DataBroker(QObject):
    """Central hub that holds the latest PLC data and notifies all consumers."""

    data_updated = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._latest: dict = {}

    @property
    def latest(self) -> dict:
        return self._latest

    def update(self, data: dict):
        self._latest = data
        self.data_updated.emit(data)
