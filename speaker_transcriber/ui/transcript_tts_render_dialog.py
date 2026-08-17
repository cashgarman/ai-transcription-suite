from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


class TranscriptTtsRenderDialog(QDialog):
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None, *, title: str = "Preparing transcript audio") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
        layout = QVBoxLayout(self)
        self.status_label = QLabel("Starting…")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self._on_cancel)
        layout.addWidget(buttons)
        self._cancelling = False
        self._finished = False
        self.resize(420, 140)

    def set_progress(self, current: int, total: int, message: str) -> None:
        if self._cancelling or self._finished:
            return
        self.status_label.setText(message)
        if total <= 0:
            self.progress_bar.setRange(0, 0)
            return
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(min(max(current, 0), total))

    def finish(self) -> None:
        """Dismiss the modal after the worker has stopped. Does not cancel."""
        if self._finished:
            return
        self._finished = True
        self.accept()

    def reject(self) -> None:
        if self._finished:
            super().reject()
            return
        self._on_cancel()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._finished:
            event.accept()
            return
        self._on_cancel()
        event.ignore()

    def _on_cancel(self) -> None:
        if self._finished or self._cancelling:
            return
        self._cancelling = True
        self.status_label.setText("Cancelling…")
        self.cancel_requested.emit()
