from __future__ import annotations

import threading


class Signal:
    """Lightweight callback-based signal (no Qt dependency)."""

    def __init__(self):
        self._callbacks: list = []
        self._lock = threading.Lock()

    def connect(self, callback):
        with self._lock:
            self._callbacks.append(callback)

    def disconnect(self, callback):
        with self._lock:
            self._callbacks.remove(callback)

    def emit(self, *args):
        with self._lock:
            callbacks = list(self._callbacks)
        for cb in callbacks:
            cb(*args)


class DataBroker:
    """Central hub that holds the latest PLC data and notifies all consumers.

    Uses plain callbacks — works without PyQt6 for headless deployments.
    """

    def __init__(self):
        self.data_updated = Signal()
        self._latest: dict = {}

    @property
    def latest(self) -> dict:
        return self._latest

    def update(self, data: dict):
        self._latest = data
        self.data_updated.emit(data)


try:
    from PyQt6.QtCore import QObject, pyqtSignal

    class QtDataBroker(QObject):
        """Qt-flavoured broker — emits a pyqtSignal so slots run on the receiver's thread."""

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

except ImportError:
    pass
