from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from speaker_transcriber.models.model_catalog import (
    CatalogEntry,
    DownloadProgress,
    format_bytes,
    format_disk_label,
)
from speaker_transcriber.models.summarization import format_approx_vram
from speaker_transcriber.ui.hazard_progress import HazardProgressBar
from speaker_transcriber.ui.worker import CatalogDownloadWorker, CatalogListWorker


def _sort_key_less(left, right) -> bool:
    if left is None and right is None:
        return False
    if left is None:
        return False
    if right is None:
        return True
    if isinstance(left, str) and isinstance(right, str):
        return left.casefold() < right.casefold()
    try:
        return left < right
    except TypeError:
        return str(left).casefold() < str(right).casefold()


class SortableTableItem(QTableWidgetItem):
    def __init__(self, label: str, sort_key=None) -> None:
        super().__init__(label)
        self.sort_key = sort_key if sort_key is not None else label

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, SortableTableItem):
            return _sort_key_less(self.sort_key, other.sort_key)
        return super().__lt__(other)


class AddModelsDialog(QDialog):
    def __init__(self, provider, parent=None, *, token: str | None = None) -> None:
        super().__init__(parent)
        self.provider = provider
        self.token = token
        self._family: str | None = None
        self._entries: list[CatalogEntry] = []
        self._list_worker: CatalogListWorker | None = None
        self._download_worker: CatalogDownloadWorker | None = None
        self._downloaded: list[str] = []
        self._sort_column = -1
        self._sort_order = Qt.SortOrder.AscendingOrder

        self.setWindowTitle(f"Add models — {provider.title}")
        self.setMinimumSize(720, 520)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search models…")
        self.search.textChanged.connect(self._schedule_search)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._run_search)

        self.back_button = QPushButton("Back to families")
        self.back_button.setVisible(False)
        self.back_button.clicked.connect(self._back_to_families)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "~VRAM", "Download", "Status"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        header.sortIndicatorChanged.connect(self._on_sort_changed)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self._update_download_enabled)
        self.table.itemDoubleClicked.connect(self._open_family)

        self.status = QLabel("Loading catalog…")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint = QLabel(self._hint_text())
        self.hint.setWordWrap(True)
        self.hint.setObjectName("fieldCaption")
        self.disk_label = QLabel()
        self.disk_bar = QProgressBar()
        self.disk_bar.setRange(0, 1000)
        self.disk_bar.setTextVisible(False)
        self.disk_bar.setFixedHeight(8)

        self.progress = HazardProgressBar()
        self.progress.setRange(0, 1000)
        self.progress_label = QLabel("0%")
        self.eta_label = QLabel("ETA —")

        self.download_button = QPushButton("Download")
        self.download_button.setObjectName("primaryButton")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self._start_download)
        self.cancel_button = QPushButton("Cancel download")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_download)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)

        search_row = QHBoxLayout()
        search_row.addWidget(self.search, 1)
        search_row.addWidget(self.back_button)

        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.progress_label)
        progress_row.addWidget(self.eta_label)

        buttons = QHBoxLayout()
        buttons.addWidget(self.download_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.status, 1)
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addLayout(search_row)
        layout.addWidget(self.hint)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.disk_label)
        layout.addWidget(self.disk_bar)
        layout.addLayout(progress_row)
        layout.addLayout(buttons)

        self._refresh_disk()
        self._run_search()

    def downloaded_names(self) -> list[str]:
        return list(self._downloaded)

    def _hint_text(self) -> str:
        kind = str(getattr(self.provider, "id", "") or "")
        if kind == "diarization":
            return (
                "This app loads pyannote pipelines (they include config.yaml). "
                "CoreML, ONNX, and similar conversions will not work. "
                "pyannote models are gated: set a Hugging Face token in Settings "
                "and accept the terms for the selected pipeline and "
                "pyannote/segmentation-3.0 on the Hub."
            )
        if kind in {"whisper", "alignment"}:
            return "Downloads are stored in the Hugging Face cache."
        return "Downloads are stored in the Ollama models directory."

    def _schedule_search(self, _text: str = "") -> None:
        self._search_timer.start(280)

    def _run_search(self) -> None:
        self._family = None
        self.back_button.setVisible(False)
        self._start_list_worker(self.search.text().strip())

    def _back_to_families(self) -> None:
        self._run_search()

    def _start_list_worker(self, query: str, family: str | None = None) -> None:
        if self._list_worker and self._list_worker.isRunning():
            self._list_worker.completed.disconnect()
            self._list_worker.failed.disconnect()
            self._list_worker.setParent(None)
            self._list_worker.finished.connect(self._list_worker.deleteLater)
        self.status.setText("Loading catalog…")
        self._list_worker = CatalogListWorker(self.provider, query, family, self)
        self._list_worker.completed.connect(self._on_listed)
        self._list_worker.failed.connect(self._on_list_failed)
        self._list_worker.start()

    def _on_listed(self, entries: list) -> None:
        self._entries = [entry for entry in entries if isinstance(entry, CatalogEntry)]
        self._populate_table()
        if self._family:
            self.status.setText(f"Tags for {self._family}")
            self.back_button.setVisible(True)
        else:
            count = len(self._entries)
            self.status.setText(f"{count} model{'s' if count != 1 else ''}")
            self.back_button.setVisible(False)
        self._refresh_disk()

    def _on_list_failed(self, message: str) -> None:
        self.status.setText(f"Could not load catalog: {message}")
        self._entries = []
        self._populate_table()

    def _on_sort_changed(self, column: int, order: Qt.SortOrder) -> None:
        self._sort_column = column
        self._sort_order = order

    def _populate_table(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for entry in self._entries:
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = SortableTableItem(entry.label, entry.label.casefold())
            name_item.setData(Qt.ItemDataRole.UserRole, entry.name)
            name_item.setData(Qt.ItemDataRole.UserRole + 1, entry.is_family)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(
                row,
                1,
                SortableTableItem(format_approx_vram(entry.size_bytes), entry.size_bytes),
            )
            self.table.setItem(
                row,
                2,
                SortableTableItem(format_bytes(entry.size_bytes), entry.size_bytes),
            )
            self.table.setItem(
                row,
                3,
                SortableTableItem(entry.status_label, entry.status_label.casefold()),
            )
        self.table.setSortingEnabled(True)
        if self._sort_column >= 0:
            self.table.sortItems(self._sort_column, self._sort_order)
        else:
            self.table.horizontalHeader().setSortIndicator(
                -1, Qt.SortOrder.AscendingOrder
            )
        self._update_download_enabled()

    def _entry_for_row(self, row: int) -> CatalogEntry | None:
        item = self.table.item(row, 0)
        if item is None:
            return None
        name = item.data(Qt.ItemDataRole.UserRole)
        for entry in self._entries:
            if entry.name == name:
                return entry
        return None

    def _selected_entries(self) -> list[CatalogEntry]:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        selected: list[CatalogEntry] = []
        for row in rows:
            entry = self._entry_for_row(row)
            if entry is not None:
                selected.append(entry)
        return selected

    def _update_download_enabled(self) -> None:
        downloading = self._download_worker is not None and self._download_worker.isRunning()
        selected = [
            entry
            for entry in self._selected_entries()
            if not entry.installed
        ]
        self.download_button.setEnabled(bool(selected) and not downloading)

    def _open_family(self, item: QTableWidgetItem) -> None:
        entry = self._entry_for_row(item.row())
        if entry is None or not entry.is_family:
            return
        self._family = entry.family or entry.name
        self.back_button.setVisible(True)
        self._start_list_worker("", self._family)

    def _start_download(self) -> None:
        selected = [
            entry.name
            for entry in self._selected_entries()
            if not entry.installed
        ]
        if not selected:
            return
        too_large = [
            entry
            for entry in self._selected_entries()
            if entry.size_bytes
            and entry.size_bytes > self.provider.disk_usage().free_bytes
        ]
        if too_large:
            names = ", ".join(entry.label for entry in too_large)
            self.status.setText(
                f"Warning: {names} may not fit on the model drive. Download will still start."
            )
        if self._download_worker and self._download_worker.isRunning():
            return
        self.cancel_button.setEnabled(True)
        self.download_button.setEnabled(False)
        self._download_worker = CatalogDownloadWorker(self.provider, selected, self)
        self._download_worker.progress.connect(self._on_progress)
        self._download_worker.model_finished.connect(self._on_model_finished)
        self._download_worker.failed.connect(self._on_download_failed)
        self._download_worker.completed.connect(self._on_download_completed)
        self._download_worker.start()

    def _cancel_download(self) -> None:
        if self._download_worker is not None:
            self._download_worker.request_cancel()
            self.status.setText(
                "Stopping download tracking. The backend may finish in the background."
            )

    def _on_progress(self, update: object) -> None:
        if not isinstance(update, DownloadProgress):
            return
        self.progress.setValue(round(update.fraction * 1000))
        self.progress_label.setText(f"{update.percent}%")
        self.eta_label.setText(f"ETA {update.eta_text}")
        self.status.setText(update.status)
        self._refresh_disk()

    def _on_model_finished(self, name: str) -> None:
        self._downloaded.append(str(name))
        for entry_index, entry in enumerate(self._entries):
            if entry.name == name:
                self._entries[entry_index] = CatalogEntry(
                    name=entry.name,
                    display_name=entry.display_name,
                    size_bytes=entry.size_bytes,
                    installed=True,
                    gated=entry.gated,
                    description=entry.description,
                    family=entry.family,
                    role=entry.role,
                    is_family=entry.is_family,
                )
        self._populate_table()

    def _on_download_failed(self, message: str) -> None:
        self.status.setText(message)
        QMessageBox.warning(self, "Download failed", message)
        self.cancel_button.setEnabled(False)
        self._update_download_enabled()

    def _on_download_completed(self) -> None:
        self.cancel_button.setEnabled(False)
        self.progress.setValue(0)
        self.progress_label.setText("0%")
        self.eta_label.setText("ETA —")
        self.status.setText("Download complete")
        self._update_download_enabled()
        self._refresh_disk()

    def _refresh_disk(self) -> None:
        try:
            usage = self.provider.disk_usage()
        except Exception:
            self.disk_label.setText("Disk space unavailable")
            return
        self.disk_label.setText(format_disk_label(usage))
        fraction = 0.0
        if usage.total_bytes > 0:
            fraction = usage.used_bytes / usage.total_bytes
        self.disk_bar.setValue(round(min(max(fraction, 0.0), 1.0) * 1000))

    def _stop_worker(self, worker) -> None:
        if worker is None:
            return
        for signal_name in ("completed", "failed", "progress", "model_finished"):
            signal = getattr(worker, signal_name, None)
            if signal is None:
                continue
            try:
                signal.disconnect()
            except (RuntimeError, TypeError):
                pass
        if hasattr(worker, "request_cancel"):
            worker.request_cancel()
        if worker.isRunning():
            worker.wait(8000)
        if worker.isRunning():
            worker.setParent(None)
            worker.finished.connect(worker.deleteLater)

    def closeEvent(self, event) -> None:
        self._stop_worker(self._download_worker)
        self._stop_worker(self._list_worker)
        super().closeEvent(event)
