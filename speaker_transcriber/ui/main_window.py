from __future__ import annotations

import logging
import time
from pathlib import Path
from queue import Empty, Queue

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import (
    QAction,
    QBrush,
    QCloseEvent,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFontMetrics,
    QKeySequence,
    QPainter,
    QPaintEvent,
    QPalette,
    QShortcut,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from speaker_transcriber.audio.ffmpeg import (
    SUPPORTED_EXTENSIONS,
    is_supported_media,
    media_file_dialog_filter,
)
from speaker_transcriber.audio.sources import MediaSource
from speaker_transcriber.cache import SpeakerNameStore, TranscriptCache
from speaker_transcriber.config import AppSettings, SettingsStore
from speaker_transcriber.export import EXPORTERS, export_result
from speaker_transcriber.export.common import (
    format_speaking_duration,
    speaker_color_map,
    speaker_speaking_seconds,
)
from speaker_transcriber.export.text_exporter import render_text
from speaker_transcriber.gpu_stats import query_gpu_stats
from speaker_transcriber.models.summarization import RequirementsSummarizer
from speaker_transcriber.pipeline.types import ProcessingOptions, ProgressUpdate, TranscriptResult
from speaker_transcriber.ui.collapsible_section import CollapsibleSection
from speaker_transcriber.ui.detachable_tab_widget import DetachableTabWidget
from speaker_transcriber.ui.duration_probe_worker import MediaDurationProbeWorker
from speaker_transcriber.ui.input_timeline import InputTimelineWidget
from speaker_transcriber.ui.ollama_model_combo import OllamaModelComboBox
from speaker_transcriber.ui.settings_dialog import SettingsDialog
from speaker_transcriber.ui.transcript_panel import TranscriptPanel
from speaker_transcriber.ui.worker import (
    OllamaModelListWorker,
    ProcessingWorker,
    SummarizationWorker,
)


class ElidedLabel(QLabel):
    """Single-line label that elides overflow instead of widening its row."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setToolTip(text)

    def setText(self, text: str) -> None:
        super().setText(text)
        self.setToolTip(text)

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        metrics = QFontMetrics(self.font())
        elided = metrics.elidedText(
            self.text(),
            Qt.TextElideMode.ElideRight,
            self.width(),
        )
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(self.rect(), int(self.alignment()), elided)
        painter.end()


class ExportDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export transcript")
        layout = QVBoxLayout(self)
        self.checkboxes = {}
        for format_name in EXPORTERS:
            checkbox = QCheckBox(format_name.upper())
            checkbox.setChecked(format_name in {"txt", "json"})
            self.checkboxes[format_name] = checkbox
            layout.addWidget(checkbox)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_formats(self) -> list[str]:
        return [
            name for name, checkbox in self.checkboxes.items() if checkbox.isChecked()
        ]


class MainWindow(QMainWindow):
    _MAX_RECENT_FILES = 12

    def __init__(
        self,
        settings_store: SettingsStore,
        log_queue: Queue[logging.LogRecord],
    ) -> None:
        super().__init__()
        self.settings_store = settings_store
        self.settings = settings_store.load()
        self.log_queue = log_queue
        self.transcript_cache = TranscriptCache()
        self.speaker_name_store = SpeakerNameStore()
        self.worker: ProcessingWorker | None = None
        self.duration_probe_worker: MediaDurationProbeWorker | None = None
        self.summary_worker: SummarizationWorker | None = None
        self.ollama_model_worker: OllamaModelListWorker | None = None
        self.result: TranscriptResult | None = None
        self.started_at = 0.0
        self._speaker_rename_pending = False
        self.setAcceptDrops(True)
        self.setWindowTitle("Summit")
        self.resize(self.settings.window_width, self.settings.window_height)
        self._build_menu_bar()
        self._build_ui()

        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.timeout.connect(self._update_elapsed)
        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self._drain_logs)
        self.log_timer.start(200)
        self.gpu_stats_timer = QTimer(self)
        self.gpu_stats_timer.timeout.connect(self._refresh_gpu_meters)
        self.gpu_stats_timer.start(1000)
        self._refresh_gpu_meters()
        self._refresh_ollama_models()

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")

        self.recent_files_menu = QMenu("Recent Files…", self)
        file_menu.addMenu(self.recent_files_menu)
        self._rebuild_recent_files_menu()

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _rebuild_recent_files_menu(self) -> None:
        self.recent_files_menu.clear()
        recent = [
            path
            for path in self.settings.recent_files
            if isinstance(path, str) and path.strip()
        ]
        if not recent:
            empty = QAction("No recent files", self)
            empty.setEnabled(False)
            self.recent_files_menu.addAction(empty)
        else:
            for path_text in recent:
                path = Path(path_text)
                action = QAction(path.name, self)
                action.setToolTip(str(path))
                action.setStatusTip(str(path))
                action.triggered.connect(
                    lambda _checked=False, value=path_text: self._open_recent_file(value)
                )
                self.recent_files_menu.addAction(action)

        self.recent_files_menu.addSeparator()
        clear_action = QAction("Clear Recent Files", self)
        clear_action.setEnabled(bool(recent))
        clear_action.triggered.connect(self._clear_recent_files)
        self.recent_files_menu.addAction(clear_action)

    def _remember_recent_files(self, paths: list[Path]) -> None:
        recent = [
            item
            for item in self.settings.recent_files
            if isinstance(item, str) and item.strip()
        ]
        for path in reversed(paths):
            if not path.is_file():
                continue
            resolved = str(path.resolve())
            recent = [item for item in recent if item != resolved]
            recent.insert(0, resolved)
        self.settings.recent_files = recent[: self._MAX_RECENT_FILES]
        self.settings_store.save(self.settings)
        self._rebuild_recent_files_menu()

    def _open_recent_file(self, path_text: str) -> None:
        path = Path(path_text)
        if not path.is_file() or not is_supported_media(path):
            self.settings.recent_files = [
                item for item in self.settings.recent_files if item != path_text
            ]
            self.settings_store.save(self.settings)
            self._rebuild_recent_files_menu()
            QMessageBox.warning(
                self,
                "Missing file",
                "That recent file is missing or no longer supported, so it was "
                "removed from the list.",
            )
            return
        self._add_source_paths([path])

    def _clear_recent_files(self) -> None:
        self.settings.recent_files = []
        self.settings_store.save(self.settings)
        self._rebuild_recent_files_menu()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        self.setup_section = CollapsibleSection("Setup", expanded=True)
        setup_layout = self.setup_section.content_layout()
        setup_layout.setContentsMargins(10, 0, 10, 8)
        setup_layout.setSpacing(6)

        self.input_timeline = InputTimelineWidget()
        self.input_timeline.order_changed.connect(self._update_cache_controls)
        setup_layout.addWidget(self.input_timeline)

        source_button_row = QHBoxLayout()
        source_button_row.setSpacing(6)
        add_files_button = QPushButton("Add files…")
        add_files_button.clicked.connect(self._browse_sources)
        remove_files_button = QPushButton("Remove selected")
        remove_files_button.clicked.connect(self._remove_selected_sources)
        self.use_cache_checkbox = QCheckBox("Use cached transcript")
        self.use_cache_checkbox.setChecked(self.settings.use_cached_transcript)
        self.use_cache_checkbox.toggled.connect(self._cache_preference_changed)
        source_button_row.addWidget(add_files_button)
        source_button_row.addWidget(remove_files_button)
        source_button_row.addStretch(1)
        source_button_row.addWidget(self.use_cache_checkbox)
        setup_layout.addLayout(source_button_row)

        self.model_combo = QComboBox()
        self.model_combo.addItem("Medium", "medium")
        self.model_combo.addItem("Distil Large V3", "distil-large-v3")
        self.model_combo.addItem("Large V3", "large-v3")
        model_index = self.model_combo.findData(self.settings.model)
        self.model_combo.setCurrentIndex(max(model_index, 0))
        self.language_combo = QComboBox()
        self.language_combo.setEditable(True)
        self.language_combo.addItems(
            ["auto", "en", "es", "fr", "de", "it", "pt", "nl", "ja", "zh", "ko"]
        )
        self.language_combo.setCurrentText(self.settings.language)
        self.speaker_mode = QComboBox()
        self.speaker_mode.addItems(["Automatic", "Exact", "Minimum / maximum"])
        self.speaker_mode.currentIndexChanged.connect(self._speaker_mode_changed)
        self.exact_speakers = QSpinBox()
        self.exact_speakers.setRange(1, 50)
        self.exact_speakers.setValue(self.settings.num_speakers or 2)
        self.min_speakers = QSpinBox()
        self.min_speakers.setRange(1, 50)
        self.min_speakers.setValue(self.settings.min_speakers or 1)
        self.max_speakers = QSpinBox()
        self.max_speakers.setRange(1, 50)
        self.max_speakers.setValue(self.settings.max_speakers or 6)
        self.exact_speakers_field = self._inline_field("Exact", self.exact_speakers)
        self.min_speakers_field = self._inline_field("Min", self.min_speakers)
        self.max_speakers_field = self._inline_field("Max", self.max_speakers)
        if self.settings.num_speakers is not None:
            self.speaker_mode.setCurrentIndex(1)
        elif self.settings.min_speakers is not None or self.settings.max_speakers is not None:
            self.speaker_mode.setCurrentIndex(2)

        self.ollama_model_combo = OllamaModelComboBox()
        self.ollama_model_combo.currentIndexChanged.connect(self._on_ollama_model_changed)
        self.refresh_ollama_button = QPushButton("Refresh")
        self.refresh_ollama_button.clicked.connect(self._refresh_ollama_models)

        options_row = QHBoxLayout()
        options_row.setSpacing(10)
        options_row.addWidget(self._inline_field("Model", self.model_combo))
        options_row.addWidget(self._inline_field("Language", self.language_combo))
        options_row.addWidget(self._inline_field("Speakers", self.speaker_mode))
        options_row.addWidget(self.exact_speakers_field)
        options_row.addWidget(self.min_speakers_field)
        options_row.addWidget(self.max_speakers_field)
        options_row.addStretch(1)
        options_row.addWidget(
            self._inline_field("Ollama", self.ollama_model_combo, stretch=1),
            2,
        )
        options_row.addWidget(self.refresh_ollama_button)
        setup_layout.addLayout(options_row)
        self._speaker_mode_changed()
        root.addWidget(self.setup_section)

        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self._start)
        self.retranscribe_button = QPushButton("Re-transcribe")
        self.retranscribe_button.setEnabled(False)
        self.retranscribe_button.clicked.connect(self._retranscribe)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)
        settings_button = QPushButton("Settings…")
        settings_button.clicked.connect(self._open_settings)
        self.export_button = QPushButton("Export…")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export)
        self.summarize_button = QPushButton("Summarize with Ollama")
        self.summarize_button.setObjectName("primaryButton")
        self.summarize_button.setEnabled(False)
        self.summarize_button.clicked.connect(self._summarize)
        action_row.addWidget(self.start_button)
        action_row.addWidget(self.retranscribe_button)
        action_row.addWidget(self.cancel_button)
        action_row.addWidget(settings_button)
        action_row.addStretch()
        action_row.addWidget(self.summarize_button)
        action_row.addWidget(self.export_button)
        root.addLayout(action_row)

        status_strip = QFrame()
        status_strip.setObjectName("statusStrip")
        status_layout = QHBoxLayout(status_strip)
        status_layout.setContentsMargins(10, 5, 10, 5)
        status_layout.setSpacing(12)
        self.stage_label = ElidedLabel("Ready")
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("jobProgressBar")
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setToolTip("Processing progress")
        self.vram_meter, self.vram_bar = self._build_status_meter("VRAM", "vramMeter")
        self.gpu_meter, self.gpu_bar = self._build_status_meter("GPU", "gpuMeter")
        self.elapsed_label = QLabel("Elapsed: 00:00")
        status_layout.addWidget(self.stage_label, 2)
        status_layout.addWidget(self.progress_bar, 2)
        status_layout.addWidget(self.vram_meter, 2)
        status_layout.addWidget(self.gpu_meter, 2)
        status_layout.addWidget(self.elapsed_label)
        root.addWidget(status_strip)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tabs = DetachableTabWidget()
        self.transcript_panel = TranscriptPanel()
        self.summary_view = QPlainTextEdit()
        self.summary_view.setPlaceholderText("An optional local Ollama summary will appear here.")
        self.tabs.add_detachable_tab(
            self.transcript_panel,
            "Transcript",
            tab_id="transcript",
        )
        self.tabs.add_detachable_tab(self.summary_view, "Summary", tab_id="summary")
        splitter.addWidget(self.tabs)

        speaker_panel = QWidget()
        speaker_layout = QVBoxLayout(speaker_panel)
        speaker_layout.addWidget(QLabel("Speakers"))
        self.speaker_table = QTableWidget(0, 3)
        self.speaker_table.setHorizontalHeaderLabels(
            ["Label", "Display name", "Spoke"]
        )
        self.speaker_table.horizontalHeader().setStretchLastSection(False)
        self.speaker_table.horizontalHeader().setSectionResizeMode(
            1, self.speaker_table.horizontalHeader().ResizeMode.Stretch
        )
        self.speaker_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.speaker_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.speaker_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.speaker_table.customContextMenuRequested.connect(
            self._on_speaker_context_menu
        )
        self.speaker_table.itemSelectionChanged.connect(
            self._on_speaker_selection_changed
        )
        self.speaker_table.itemChanged.connect(self._on_speaker_name_edited)
        self._speaker_table_base_palette = QPalette(self.speaker_table.palette())
        speaker_layout.addWidget(self.speaker_table)

        speaker_nav_row = QHBoxLayout()
        style = self.style()
        self.first_speaker_entry_button = QPushButton("First")
        self.first_speaker_entry_button.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward)
        )
        self.first_speaker_entry_button.setToolTip(
            "Jump to the first transcript entry for the selected speaker (Home)"
        )
        self.first_speaker_entry_button.setEnabled(False)
        self.first_speaker_entry_button.clicked.connect(
            lambda: self._goto_speaker_entry_edge(first=True)
        )
        self.prev_speaker_entry_button = QPushButton("Prev")
        self.prev_speaker_entry_button.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_MediaSeekBackward)
        )
        self.prev_speaker_entry_button.setToolTip(
            "Jump to the previous transcript entry for the selected speaker "
            "(Up / Page Up)"
        )
        self.prev_speaker_entry_button.setEnabled(False)
        self.prev_speaker_entry_button.clicked.connect(
            lambda: self._goto_speaker_entry(-1)
        )
        self.next_speaker_entry_button = QPushButton("Next")
        self.next_speaker_entry_button.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_MediaSeekForward)
        )
        self.next_speaker_entry_button.setToolTip(
            "Jump to the next transcript entry for the selected speaker "
            "(Down / Page Down)"
        )
        self.next_speaker_entry_button.setEnabled(False)
        self.next_speaker_entry_button.clicked.connect(
            lambda: self._goto_speaker_entry(1)
        )
        self.last_speaker_entry_button = QPushButton("Last")
        self.last_speaker_entry_button.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward)
        )
        self.last_speaker_entry_button.setToolTip(
            "Jump to the last transcript entry for the selected speaker (End)"
        )
        self.last_speaker_entry_button.setEnabled(False)
        self.last_speaker_entry_button.clicked.connect(
            lambda: self._goto_speaker_entry_edge(first=False)
        )
        speaker_nav_row.addWidget(self.first_speaker_entry_button)
        speaker_nav_row.addWidget(self.prev_speaker_entry_button)
        speaker_nav_row.addWidget(self.next_speaker_entry_button)
        speaker_nav_row.addWidget(self.last_speaker_entry_button)
        speaker_layout.addLayout(speaker_nav_row)

        splitter.addWidget(speaker_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        self.log_section = CollapsibleSection(
            "Error and processing log",
            expanded=False,
        )
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(120)
        self.log_output.setPlaceholderText("Processing messages and errors will appear here.")
        self.log_section.add_widget(self.log_output)
        root.addWidget(self.log_section)

        self.setCentralWidget(central)
        self._bind_speaker_nav_shortcuts()
        self._update_cache_controls()

    @staticmethod
    def _inline_field(label_text: str, widget: QWidget, stretch: int = 0) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        caption = QLabel(label_text)
        caption.setObjectName("fieldCaption")
        layout.addWidget(caption)
        layout.addWidget(widget, stretch)
        return container

    def _build_status_meter(
        self,
        title: str,
        object_name: str,
    ) -> tuple[QWidget, QProgressBar]:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        caption = QLabel(title)
        caption.setObjectName("meterCaption")
        bar = QProgressBar()
        bar.setObjectName(object_name)
        bar.setRange(0, 1000)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        layout.addWidget(caption)
        layout.addWidget(bar)
        return container, bar

    def _refresh_gpu_meters(self) -> None:
        stats = query_gpu_stats()
        if not stats.available:
            self.vram_bar.setValue(0)
            self.gpu_bar.setValue(0)
            self.vram_bar.setToolTip("GPU VRAM unavailable")
            self.gpu_bar.setToolTip("GPU compute unavailable")
            return
        vram_fraction = (
            stats.vram_used_mb / stats.vram_total_mb if stats.vram_total_mb else 0.0
        )
        self.vram_bar.setValue(round(max(0.0, min(vram_fraction, 1.0)) * 1000))
        self.gpu_bar.setValue(round(stats.gpu_util_percent * 10))
        self.vram_bar.setToolTip(
            f"VRAM {stats.vram_used_mb / 1024:.1f} / "
            f"{stats.vram_total_mb / 1024:.1f} GB"
        )
        self.gpu_bar.setToolTip(f"GPU compute {stats.gpu_util_percent}%")

    def _cache_preference_changed(self, checked: bool) -> None:
        self.settings.use_cached_transcript = checked
        self.settings_store.save(self.settings)

    def _source_paths(self) -> list[Path]:
        return self.input_timeline.paths()

    def _current_sources(self) -> list[Path] | None:
        paths = self._source_paths()
        if not paths:
            return None
        if all(path.is_file() and is_supported_media(path) for path in paths):
            return paths
        return None

    def _validate_source_input(self) -> list[Path] | None:
        paths = self._source_paths()
        if not paths:
            QMessageBox.warning(
                self,
                "Invalid input",
                "Add one or more audio or video files from the same conversation.",
            )
            return None
        invalid_paths = [
            path for path in paths if not path.is_file() or not is_supported_media(path)
        ]
        if invalid_paths:
            formats = ", ".join(
                extension.lstrip(".") for extension in sorted(SUPPORTED_EXTENSIONS)
            )
            details = "\n".join(f"- {path.name}" for path in invalid_paths[:5])
            extra = ""
            if len(invalid_paths) > 5:
                extra = f"\n…and {len(invalid_paths) - 5} more"
            QMessageBox.warning(
                self,
                "Unsupported format",
                "One or more selected files are missing or unsupported.\n\n"
                f"{details}{extra}\n\nSupported formats: {formats}",
            )
            return None
        return paths

    def _add_source_paths(self, paths: list[Path]) -> None:
        self.input_timeline.append_paths(paths)
        self._probe_durations(paths)
        self._remember_recent_files(paths)
        self._update_cache_controls()

    def _probe_durations(self, paths: list[Path]) -> None:
        pending = [
            str(path.resolve())
            for path in paths
            if path.is_file() and is_supported_media(path)
        ]
        if not pending:
            return
        if self.duration_probe_worker and self.duration_probe_worker.isRunning():
            self.duration_probe_worker.requestInterruption()
            self.duration_probe_worker.wait(1000)
        self.duration_probe_worker = MediaDurationProbeWorker(pending, self)
        self.duration_probe_worker.duration_ready.connect(self._on_duration_ready)
        self.duration_probe_worker.start()

    def _on_duration_ready(self, resolved_path: str, duration_seconds: float) -> None:
        self.input_timeline.set_duration(Path(resolved_path), duration_seconds)

    def _remove_selected_sources(self) -> None:
        selected = self.input_timeline.selected_paths()
        if not selected:
            return
        self.input_timeline.remove_selected(selected)
        self._update_cache_controls()

    def _update_cache_controls(self) -> None:
        sources = self._current_sources()
        cache_available = sources is not None and self.transcript_cache.exists(sources)
        busy = (
            (self.worker is not None and self.worker.isRunning())
            or (self.summary_worker is not None and self.summary_worker.isRunning())
        )
        self.retranscribe_button.setEnabled(cache_available and not busy)

    def _cache_status_message(self, result: TranscriptResult, sources: list[Path]) -> str:
        cached_paths = [
            str(Path(path).resolve())
            for path in (result.source_files or [result.source_file])
        ]
        current_paths = [str(path.resolve()) for path in sources]
        if cached_paths == current_paths:
            if len(current_paths) > 1:
                return f"Loaded from cache ({len(current_paths)} merged files)"
            return "Loaded from cache"
        return f"Loaded from cache (original input: {result.source_name})"

    def _speaker_mode_changed(self) -> None:
        mode = self.speaker_mode.currentIndex()
        self.exact_speakers.setEnabled(mode == 1)
        self.min_speakers.setEnabled(mode == 2)
        self.max_speakers.setEnabled(mode == 2)
        self.exact_speakers_field.setVisible(mode == 1)
        self.min_speakers_field.setVisible(mode == 2)
        self.max_speakers_field.setVisible(mode == 2)

    def _browse_sources(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select audio or video files",
            "",
            media_file_dialog_filter(),
        )
        if paths:
            self._add_source_paths([Path(path) for path in paths])

    def _supported_drop_paths(self, event: QDropEvent | QDragEnterEvent) -> list[Path]:
        paths: list[Path] = []
        seen: set[str] = set()
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if not path.is_file() or not is_supported_media(path):
                continue
            resolved = str(path.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            paths.append(path)
        return paths

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._supported_drop_paths(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = self._supported_drop_paths(event)
        if paths:
            self._add_source_paths(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def _processing_options(self) -> ProcessingOptions:
        mode = self.speaker_mode.currentIndex()
        return ProcessingOptions(
            model=str(self.model_combo.currentData()),
            device="cuda",
            compute_type=self.settings.compute_type,
            batch_size=self.settings.batch_size,
            language=self.language_combo.currentText().strip() or "auto",
            num_speakers=self.exact_speakers.value() if mode == 1 else None,
            min_speakers=self.min_speakers.value() if mode == 2 else None,
            max_speakers=self.max_speakers.value() if mode == 2 else None,
            alignment_device=self.settings.alignment_device,
            diarization_device=self.settings.diarization_device,
            merge_gap_seconds=self.settings.merge_gap_seconds,
            max_block_duration_seconds=self.settings.max_block_duration_seconds,
            inherit_speaker_threshold_seconds=(
                self.settings.inherit_speaker_threshold_seconds
            ),
            hf_token=self.settings_store.get_hf_token(),
        )

    def _start(self) -> None:
        sources = self._validate_source_input()
        if sources is None:
            return
        if self.use_cache_checkbox.isChecked():
            cached = self.transcript_cache.load(sources)
            if cached is not None:
                self._load_from_cache(cached, sources)
                return
        self._run_transcription(sources)

    def _retranscribe(self) -> None:
        sources = self._validate_source_input()
        if sources is None:
            return
        self._run_transcription(sources)

    def _load_from_cache(self, result: TranscriptResult, sources: list[Path]) -> None:
        self.result = result
        self.transcript_panel.clear()
        self.summary_view.clear()
        self.progress_bar.setValue(1000)
        self.stage_label.setText(self._cache_status_message(result, sources))
        self.elapsed_label.setText("Elapsed: 00:00")
        self._refresh_gpu_meters()
        self._show_result(sources)
        self._set_busy(False)

    def _run_transcription(self, sources: list[Path]) -> None:
        options = self._processing_options()
        if not options.hf_token:
            QMessageBox.information(
                self,
                "Diarization setup required",
                "No Hugging Face token was found. Transcription will continue, but speaker "
                "diarization may be unavailable. Add a token in Settings and accept the "
                "model terms for both pyannote/speaker-diarization-3.1 and "
                "pyannote/segmentation-3.0 on Hugging Face.",
            )
        self.settings.model = options.model
        self.settings.language = options.language
        self.settings.num_speakers = options.num_speakers
        self.settings.min_speakers = options.min_speakers
        self.settings.max_speakers = options.max_speakers
        self.settings_store.save(self.settings)
        self.result = None
        self.transcript_panel.clear()
        self.summary_view.clear()
        self.progress_bar.setValue(0)
        self.started_at = time.monotonic()
        self.elapsed_timer.start(1000)
        self._set_busy(True)
        self.worker = ProcessingWorker(
            [str(path) for path in sources],
            options,
            self,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.completed.connect(self._on_completed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _cancel(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.request_cancel()
            self.stage_label.setText("Cancellation requested; waiting for a safe boundary…")
            self.cancel_button.setEnabled(False)

    def _on_progress(self, update: ProgressUpdate) -> None:
        self.progress_bar.setValue(round(update.progress * 1000))
        self.stage_label.setText(update.message)
        if update.vram_total_mb:
            vram_fraction = update.vram_used_mb / update.vram_total_mb
            self.vram_bar.setValue(round(max(0.0, min(vram_fraction, 1.0)) * 1000))
            self.vram_bar.setToolTip(
                f"VRAM {update.vram_used_mb / 1024:.1f} / "
                f"{update.vram_total_mb / 1024:.1f} GB"
            )
        self.elapsed_label.setText(
            f"Elapsed: {self._format_elapsed(update.elapsed_seconds)}"
        )

    def _on_completed(self, result: TranscriptResult) -> None:
        self.result = result
        sources = self._source_paths()
        self._apply_session_speaker_names(sources or None)
        try:
            self.transcript_cache.save(self.result)
        except OSError as exc:
            self.log_output.appendPlainText(f"Failed to save transcript cache: {exc}")
        try:
            self._persist_speaker_names(sources or None)
        except OSError as exc:
            self.log_output.appendPlainText(f"Failed to save speaker names: {exc}")
        self.progress_bar.setValue(1000)
        configuration = result.fallback_config
        self.stage_label.setText(
            "Complete — "
            f"{configuration.get('model', 'model unknown')}, "
            f"batch {configuration.get('batch_size', '?')}, "
            f"alignment {configuration.get('alignment_device', '?')}, "
            f"diarization {configuration.get('diarization_device', '?')}"
        )
        self._show_result(self._source_paths())
        self._set_busy(False)
        decisions = result.fallback_config.get("decisions", [])
        if decisions:
            self.log_output.appendPlainText("\n".join(decisions))

    def _on_cancelled(self, partial_result: TranscriptResult | None) -> None:
        self.result = partial_result
        self.stage_label.setText(
            "Cancelled; partial transcript preserved"
            if partial_result
            else "Cancelled"
        )
        if partial_result:
            self._show_result(self._source_paths())
        self._set_busy(False)

    def _on_failed(self, message: str) -> None:
        self.stage_label.setText("Processing failed")
        self.log_output.appendPlainText(message)
        self.log_section.set_expanded(True)
        QMessageBox.critical(self, "Processing failed", message)
        self._set_busy(False)

    def _set_busy(self, busy: bool, summarizing: bool = False) -> None:
        self.start_button.setEnabled(not busy and not summarizing)
        self.cancel_button.setEnabled(busy)
        self._update_cache_controls()
        self.export_button.setEnabled(not busy and not summarizing and self.result is not None)
        ollama_ready = self.ollama_model_combo.has_selectable_model()
        self.summarize_button.setEnabled(
            not busy and not summarizing and self.result is not None and ollama_ready
        )
        self.refresh_ollama_button.setEnabled(not busy and not summarizing)
        if not busy and not summarizing:
            self.elapsed_timer.stop()

    def _apply_session_speaker_names(self, sources: list[Path] | None = None) -> None:
        if self.result is None:
            return
        source_paths = sources or self._source_paths()
        if not source_paths:
            return
        self.result.speakers = self.speaker_name_store.apply_to_names(
            source_paths,
            self.result.speakers,
        )

    def _persist_speaker_names(self, sources: list[Path] | None = None) -> None:
        if self.result is None:
            return
        source_paths = sources or self._source_paths()
        if not source_paths:
            return
        self.speaker_name_store.save(source_paths, self.result.speakers)

    def _show_result(self, sources: list[Path] | None = None) -> None:
        self._apply_session_speaker_names(sources)
        self.transcript_panel.set_result(self.result)
        self._populate_speaker_table()
        self.transcript_panel.highlight_speaker(None)
        self.export_button.setEnabled(self.result is not None)
        self._refresh_ollama_models()
        self._set_busy(False)

    def _selected_speaker_label(self) -> str | None:
        selected_rows = self.speaker_table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        label_item = self.speaker_table.item(selected_rows[0].row(), 0)
        return label_item.text() if label_item else None

    def _on_speaker_selection_changed(self) -> None:
        label = self._selected_speaker_label()
        self._apply_speaker_selection_highlight(label)
        self.transcript_panel.highlight_speaker(label)
        self._update_speaker_nav_controls()

    def _apply_speaker_selection_highlight(self, speaker_id: str | None) -> None:
        palette = QPalette(self._speaker_table_base_palette)
        if speaker_id and self.result is not None:
            colors = speaker_color_map(self.result)
            highlight = QColor(colors.get(speaker_id, "#546E7A"))
            palette.setColor(QPalette.ColorRole.Highlight, highlight)
            palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        self.speaker_table.setPalette(palette)

    def _update_speaker_nav_controls(self) -> None:
        enabled = self._selected_speaker_label() is not None and self.result is not None
        self.first_speaker_entry_button.setEnabled(enabled)
        self.prev_speaker_entry_button.setEnabled(enabled)
        self.next_speaker_entry_button.setEnabled(enabled)
        self.last_speaker_entry_button.setEnabled(enabled)

    def _speaker_nav_shortcuts_blocked(self) -> bool:
        focus = QApplication.focusWidget()
        if focus is None:
            return False
        # Keep typing intact in name fields and numeric controls; allow
        # navigation keys while the transcript itself is focused.
        return isinstance(focus, (QLineEdit, QAbstractSpinBox))

    def _bind_speaker_nav_shortcuts(self) -> None:
        bindings = (
            (
                Qt.Key.Key_Home,
                lambda: self._goto_speaker_entry_edge(first=True, from_shortcut=True),
            ),
            (
                Qt.Key.Key_End,
                lambda: self._goto_speaker_entry_edge(first=False, from_shortcut=True),
            ),
            (Qt.Key.Key_Up, lambda: self._goto_speaker_entry(-1, from_shortcut=True)),
            (
                Qt.Key.Key_PageUp,
                lambda: self._goto_speaker_entry(-1, from_shortcut=True),
            ),
            (Qt.Key.Key_Down, lambda: self._goto_speaker_entry(1, from_shortcut=True)),
            (
                Qt.Key.Key_PageDown,
                lambda: self._goto_speaker_entry(1, from_shortcut=True),
            ),
        )
        for key, callback in bindings:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(callback)

    def _goto_speaker_entry(self, delta: int, *, from_shortcut: bool = False) -> None:
        if from_shortcut and self._speaker_nav_shortcuts_blocked():
            return
        label = self._selected_speaker_label()
        if not label:
            return
        self.tabs.ensure_visible(self.transcript_panel)
        self.transcript_panel.goto_adjacent_speaker_entry(label, delta)

    def _goto_speaker_entry_edge(
        self,
        *,
        first: bool,
        from_shortcut: bool = False,
    ) -> None:
        if from_shortcut and self._speaker_nav_shortcuts_blocked():
            return
        label = self._selected_speaker_label()
        if not label:
            return
        self.tabs.ensure_visible(self.transcript_panel)
        self.transcript_panel.goto_speaker_entry_edge(label, first=first)

    def _on_speaker_context_menu(self, position) -> None:
        index = self.speaker_table.indexAt(position)
        if not index.isValid():
            return
        self.speaker_table.selectRow(index.row())
        label = self._selected_speaker_label()
        if not label:
            return
        menu = QMenu(self)
        remove_action = menu.addAction(f"Remove {label} and their transcript entries")
        chosen = menu.exec(self.speaker_table.viewport().mapToGlobal(position))
        if chosen is remove_action:
            self._remove_speaker(label)

    def _remove_speaker(self, speaker_id: str) -> None:
        if self.result is None:
            return
        display_name = self.result.speakers.get(speaker_id, speaker_id)
        answer = QMessageBox.question(
            self,
            "Remove speaker",
            (
                f'Remove "{display_name}" ({speaker_id}) and delete all of their '
                "entries from the transcript?\n\nThis cannot be undone except by "
                "reloading a cached or exported copy."
            ),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.result.remove_speaker(speaker_id)
        try:
            self.transcript_cache.save(self.result)
        except OSError as exc:
            self.log_output.appendPlainText(f"Failed to save transcript cache: {exc}")
        try:
            self._persist_speaker_names()
        except OSError as exc:
            self.log_output.appendPlainText(f"Failed to save speaker names: {exc}")
        self._populate_speaker_table()
        self.transcript_panel.set_result(self.result)
        self.transcript_panel.highlight_speaker(None)
        self.export_button.setEnabled(True)

    def _populate_speaker_table(self, selected_speaker: str | None = None) -> None:
        self.speaker_table.blockSignals(True)
        self.speaker_table.setRowCount(0)
        if self.result is None:
            self.speaker_table.blockSignals(False)
            self._apply_speaker_selection_highlight(None)
            self._update_speaker_nav_controls()
            return
        colors = speaker_color_map(self.result)
        speaking_seconds = speaker_speaking_seconds(self.result)
        speaker_labels = list(self.result.speakers.keys())
        for label in sorted(speaking_seconds):
            if label not in speaker_labels:
                speaker_labels.append(label)
        for row, label in enumerate(speaker_labels):
            name = self.result.speakers.get(label, label)
            self.speaker_table.insertRow(row)
            label_item = QTableWidgetItem(label)
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.speaker_table.setItem(row, 0, label_item)
            name_item = QTableWidgetItem(name)
            name_item.setForeground(QBrush(QColor(colors.get(label, "#B0BEC5"))))
            self.speaker_table.setItem(row, 1, name_item)
            duration_item = QTableWidgetItem(
                format_speaking_duration(speaking_seconds.get(label, 0.0))
            )
            duration_item.setFlags(duration_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            duration_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.speaker_table.setItem(row, 2, duration_item)
        self.speaker_table.blockSignals(False)
        if selected_speaker:
            for row in range(self.speaker_table.rowCount()):
                label_item = self.speaker_table.item(row, 0)
                if label_item and label_item.text() == selected_speaker:
                    self.speaker_table.selectRow(row)
                    break
            else:
                self.speaker_table.clearSelection()
                self._apply_speaker_selection_highlight(None)
        else:
            self.speaker_table.clearSelection()
            self._apply_speaker_selection_highlight(None)
        self._update_speaker_nav_controls()

    def _apply_speaker_name_colors(self) -> None:
        if self.result is None:
            return
        colors = speaker_color_map(self.result)
        for row in range(self.speaker_table.rowCount()):
            label_item = self.speaker_table.item(row, 0)
            name_item = self.speaker_table.item(row, 1)
            if label_item and name_item:
                name_item.setForeground(
                    QBrush(QColor(colors.get(label_item.text(), "#B0BEC5")))
                )

    def _refresh_ollama_models(self) -> None:
        if self.ollama_model_worker and self.ollama_model_worker.isRunning():
            return
        self.ollama_model_combo.set_placeholder("Loading models…", enabled=False)
        self.summarize_button.setEnabled(False)
        self.ollama_model_worker = OllamaModelListWorker(self)
        self.ollama_model_worker.completed.connect(self._on_ollama_models_loaded)
        self.ollama_model_worker.failed.connect(self._on_ollama_models_failed)
        self.ollama_model_worker.start()

    def _on_ollama_model_changed(self, _index: int = 0) -> None:
        self._persist_ollama_model_selection()

    def _persist_ollama_model_selection(self, *, save: bool = True) -> None:
        model_name = self.ollama_model_combo.current_model_name()
        if not model_name:
            return
        if self.settings.ollama_model == model_name:
            return
        self.settings.ollama_model = str(model_name)
        if save:
            self.settings_store.save(self.settings)

    def _on_ollama_models_loaded(self, models: list) -> None:
        from speaker_transcriber.models.summarization import OllamaModelInfo

        if not models:
            self.ollama_model_combo.set_placeholder("No models installed", enabled=False)
            self.summarize_button.setEnabled(False)
            self.summarize_button.setToolTip(
                "Install a model with `ollama pull` and click Refresh."
            )
            return
        model_infos = [
            model if isinstance(model, OllamaModelInfo) else OllamaModelInfo(str(model))
            for model in models
        ]
        self.ollama_model_combo.setEnabled(True)
        self.ollama_model_combo.blockSignals(True)
        self.ollama_model_combo.set_models(model_infos)
        self.ollama_model_combo.select_preferred_model(
            [
                self.settings.ollama_model,
                RequirementsSummarizer.MODEL_NAME,
            ]
        )
        self.ollama_model_combo.blockSignals(False)
        self.summarize_button.setToolTip("")
        self._set_busy(False)

    def _on_ollama_models_failed(self, message: str) -> None:
        self.ollama_model_combo.set_placeholder("Ollama unavailable", enabled=False)
        self.summarize_button.setEnabled(False)
        self.summarize_button.setToolTip(
            "Start Ollama locally, then click Refresh to load available models."
        )
        self.log_output.appendPlainText(f"Ollama model list failed: {message}")
        self._set_busy(False)

    def _on_speaker_name_edited(self, item: QTableWidgetItem) -> None:
        if self.result is None or item.column() != 1:
            return
        if self._speaker_rename_pending:
            return
        self._speaker_rename_pending = True
        selected_speaker = self._selected_speaker_label()
        self.tabs.ensure_visible(self.transcript_panel)
        self.transcript_panel.set_busy(True)
        QApplication.processEvents()
        QTimer.singleShot(
            0,
            lambda: self._finish_speaker_rename(selected_speaker),
        )

    def _finish_speaker_rename(self, selected_speaker: str | None) -> None:
        try:
            self._apply_speaker_names(
                save_only=False,
                selected_speaker=selected_speaker,
            )
        finally:
            self.transcript_panel.set_busy(False)
            self._speaker_rename_pending = False

    def _apply_speaker_names(
        self,
        save_only: bool = False,
        selected_speaker: str | None = None,
    ) -> None:
        if self.result is None:
            return
        if selected_speaker is None:
            selected_speaker = self._selected_speaker_label()
        for row in range(self.speaker_table.rowCount()):
            label_item = self.speaker_table.item(row, 0)
            name_item = self.speaker_table.item(row, 1)
            if label_item and name_item and name_item.text().strip():
                self.result.speakers[label_item.text()] = name_item.text().strip()
        if not save_only:
            self.transcript_panel.set_result(self.result)
            self._apply_speaker_name_colors()
            if selected_speaker:
                for row in range(self.speaker_table.rowCount()):
                    label_item = self.speaker_table.item(row, 0)
                    if label_item and label_item.text() == selected_speaker:
                        self.speaker_table.selectRow(row)
                        break
                self.transcript_panel.highlight_speaker(selected_speaker)
        try:
            self.transcript_cache.save(self.result)
        except OSError as exc:
            self.log_output.appendPlainText(f"Failed to save transcript cache: {exc}")
        try:
            self._persist_speaker_names()
        except OSError as exc:
            self.log_output.appendPlainText(f"Failed to save speaker names: {exc}")

    def _export(self) -> None:
        if self.result is None:
            return
        dialog = ExportDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        formats = dialog.selected_formats()
        if not formats:
            QMessageBox.information(self, "Export", "Select at least one format.")
            return
        export_source = (
            self.result.source_files[0]
            if self.result.source_files
            else self.result.source_file
        )
        initial = self.settings.output_directory or str(
            Path(export_source).parent / "output"
        )
        directory = QFileDialog.getExistingDirectory(self, "Export directory", initial)
        if not directory:
            return
        try:
            self.stage_label.setText("Exporting files…")
            paths = export_result(self.result, directory, formats)
            self.stage_label.setText("Export complete")
            QMessageBox.information(
                self,
                "Export complete",
                "\n".join(str(path) for path in paths),
            )
        except Exception as exc:
            self.stage_label.setText("Export failed")
            QMessageBox.critical(self, "Export failed", str(exc))

    def _open_settings(self) -> None:
        try:
            SettingsDialog(self.settings, self.settings_store, self).exec()
        except Exception as exc:
            QMessageBox.critical(self, "Settings error", str(exc))

    def _summarize(self) -> None:
        if self.result is None or (
            self.summary_worker and self.summary_worker.isRunning()
        ):
            return
        model_name = self.ollama_model_combo.current_model_name()
        if not model_name:
            QMessageBox.warning(
                self,
                "Ollama unavailable",
                "Select an available Ollama model before summarizing.",
            )
            return
        self._persist_ollama_model_selection()
        self.summary_view.setPlainText("Generating summary…\n")
        self.tabs.ensure_visible(self.summary_view)
        self.progress_bar.setValue(0)
        self.started_at = time.monotonic()
        self.elapsed_timer.start(1000)
        self.stage_label.setText("Starting summarization…")
        self._set_busy(False, summarizing=True)
        self.summary_worker = SummarizationWorker(
            render_text(self.result),
            str(model_name),
            self,
        )
        self.summary_worker.progress.connect(self._on_summary_progress)
        self.summary_worker.chunk.connect(self._on_summary_chunk)
        self.summary_worker.section_break.connect(self._on_summary_section_break)
        self.summary_worker.completed.connect(self._summary_completed)
        self.summary_worker.failed.connect(self._summary_failed)
        self.summary_worker.start()

    def _on_summary_progress(self, update: object) -> None:
        from speaker_transcriber.models.summarization import SummarizationProgress

        if not isinstance(update, SummarizationProgress):
            return
        self.progress_bar.setValue(round(update.fraction * 1000))
        self.stage_label.setText(update.message)

    def _on_summary_chunk(self, text: str) -> None:
        cursor = self.summary_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.summary_view.setTextCursor(cursor)
        self.summary_view.ensureCursorVisible()

    def _on_summary_section_break(self) -> None:
        self._on_summary_chunk("\n\n")

    def _summary_completed(self, text: str) -> None:
        if text.strip():
            self.summary_view.setPlainText(text)
        else:
            self.summary_view.setPlainText(
                "Summary failed: Ollama returned an empty response. "
                "Try a non-reasoning model or click Summarize again."
            )
        self.progress_bar.setValue(1000)
        self.stage_label.setText("Summary complete" if text.strip() else "Summary failed")
        self._set_busy(False)

    def _summary_failed(self, message: str) -> None:
        self.summary_view.setPlainText(f"Summary failed: {message}")
        self.log_output.appendPlainText(f"Summarization failed: {message}")
        self.log_section.set_expanded(True)
        self.progress_bar.setValue(0)
        self.stage_label.setText("Summary failed")
        self._set_busy(False)

    def _update_elapsed(self) -> None:
        self.elapsed_label.setText(
            f"Elapsed: {self._format_elapsed(time.monotonic() - self.started_at)}"
        )

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        minutes, secs = divmod(max(0, int(seconds)), 60)
        hours, minutes = divmod(minutes, 60)
        return (
            f"{hours:02d}:{minutes:02d}:{secs:02d}"
            if hours
            else f"{minutes:02d}:{secs:02d}"
        )

    def _drain_logs(self) -> None:
        while True:
            try:
                record = self.log_queue.get_nowait()
            except Empty:
                return
            self.log_output.appendPlainText(
                f"{record.levelname}: {record.getMessage()}"
            )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker and self.worker.isRunning():
            answer = QMessageBox.question(
                self,
                "Processing is active",
                "Cancel processing and close the application?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.worker.request_cancel()
            self.worker.wait(5000)
        if self.summary_worker and self.summary_worker.isRunning():
            answer = QMessageBox.question(
                self,
                "Summarization is active",
                "Stop summarization and close the application?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.summary_worker.wait(5000)
        self.tabs.dock_all()
        self.settings.window_width = self.width()
        self.settings.window_height = self.height()
        self._persist_ollama_model_selection(save=False)
        self.settings_store.save(self.settings)
        event.accept()
