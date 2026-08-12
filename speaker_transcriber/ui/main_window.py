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
    QFont,
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
    QGridLayout,
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
    QSlider,
    QSpinBox,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
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
from speaker_transcriber.config import (
    AppSettings,
    SettingsStore,
    OLLAMA_CTX_CHOICES,
    SPEAKER_MODES,
    format_ctx_label,
    snap_ollama_num_ctx,
)
from speaker_transcriber.export import EXPORTERS, export_result
from speaker_transcriber.export.common import (
    format_speaking_duration,
    speaker_color_map,
    speaker_speaking_seconds,
)
from speaker_transcriber.export.meeting_document import is_usable_summary_markdown
from speaker_transcriber.export.text_exporter import render_text
from speaker_transcriber.gpu_stats import query_gpu_stats
from speaker_transcriber.host_stats import query_host_stats
from speaker_transcriber.models.summarization import RequirementsSummarizer
from speaker_transcriber.pipeline.types import ProcessingOptions, ProgressUpdate, TranscriptResult
from speaker_transcriber.ui.branding import summit_icon
from speaker_transcriber.ui.collapsible_section import CollapsibleSection
from speaker_transcriber.ui.detachable_tab_widget import DetachableTabWidget
from speaker_transcriber.ui.duration_probe_worker import MediaDurationProbeWorker
from speaker_transcriber.ui.input_timeline import InputTimelineWidget
from speaker_transcriber.ui.notification import NotificationBanner
from speaker_transcriber.ui.ollama_model_combo import OllamaModelComboBox
from speaker_transcriber.ui.settings_dialog import SettingsDialog
from speaker_transcriber.ui.text_search import SearchableTextPanel
from speaker_transcriber.ui.transcript_panel import TranscriptPanel
from speaker_transcriber.ui.worker import (
    OllamaModelListWorker,
    PdfExportWorker,
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
        rect = self.contentsRect()
        elided = metrics.elidedText(
            self.text(),
            Qt.TextElideMode.ElideRight,
            rect.width(),
        )
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(rect, int(self.alignment()), elided)
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
        self.pdf_export_worker: PdfExportWorker | None = None
        self.ollama_model_worker: OllamaModelListWorker | None = None
        self.result: TranscriptResult | None = None
        self.summary_markdown = ""
        self._pdf_streaming_summary = False
        self.started_at = 0.0
        self._speaker_rename_pending = False
        self._filtered_speaker: str | None = None
        self._autoload_in_progress = False
        self.setAcceptDrops(True)
        self.setWindowTitle("Summit")
        self.setWindowIcon(summit_icon())
        self.resize(self.settings.window_width, self.settings.window_height)
        self._build_menu_bar()
        self._build_ui()
        self.notifications = NotificationBanner(self.centralWidget() or self)

        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.timeout.connect(self._update_elapsed)
        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self._drain_logs)
        self.log_timer.start(200)
        self.gpu_stats_timer = QTimer(self)
        self.gpu_stats_timer.timeout.connect(self._refresh_resource_meters)
        self.gpu_stats_timer.start(1000)
        self._refresh_resource_meters()
        self._refresh_ollama_models()

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")

        self.recent_files_menu = QMenu("Recent Files…", self)
        file_menu.addMenu(self.recent_files_menu)
        self._rebuild_recent_files_menu()

        file_menu.addSeparator()
        reload_prompts_action = QAction("Reload System Prompts", self)
        reload_prompts_action.triggered.connect(self._reload_system_prompts)
        file_menu.addAction(reload_prompts_action)

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _reload_system_prompts(self) -> None:
        from speaker_transcriber.prompts import prompts_dir, reload_prompts

        try:
            loaded = reload_prompts()
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Reload failed",
                f"Could not reload system prompts:\n{exc}",
            )
            return
        QMessageBox.information(
            self,
            "Prompts reloaded",
            f"Reloaded {len(loaded)} prompt(s) from:\n{prompts_dir()}",
        )

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
        self.input_timeline.order_changed.connect(self._on_sources_changed)

        add_files_button = QPushButton("Add files…")
        add_files_button.clicked.connect(self._browse_sources)
        remove_files_button = QPushButton("Remove selected")
        remove_files_button.clicked.connect(self._remove_selected_sources)
        file_buttons = QVBoxLayout()
        file_buttons.setContentsMargins(0, 0, 0, 0)
        file_buttons.setSpacing(6)
        file_buttons.addStretch(1)
        file_buttons.addWidget(add_files_button)
        file_buttons.addWidget(remove_files_button)
        file_buttons.addStretch(1)

        timeline_row = QHBoxLayout()
        timeline_row.setSpacing(8)
        timeline_row.addWidget(self.input_timeline, 1)
        timeline_row.addLayout(file_buttons)
        setup_layout.addLayout(timeline_row)

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
        mode_index = 0
        if self.settings.speaker_mode in SPEAKER_MODES:
            mode_index = SPEAKER_MODES.index(self.settings.speaker_mode)
        self.speaker_mode.setCurrentIndex(mode_index)
        self.speaker_mode.currentIndexChanged.connect(self._speaker_mode_changed)
        self.speaker_mode.currentIndexChanged.connect(self._persist_speaker_settings)
        self.exact_speakers.valueChanged.connect(self._persist_speaker_settings)
        self.min_speakers.valueChanged.connect(self._persist_speaker_settings)
        self.max_speakers.valueChanged.connect(self._persist_speaker_settings)

        self.ollama_model_combo = OllamaModelComboBox()
        self.ollama_model_combo.currentIndexChanged.connect(self._on_ollama_model_changed)
        self.refresh_ollama_button = QPushButton("Refresh")
        self.refresh_ollama_button.clicked.connect(self._refresh_ollama_models)
        self._ctx_choices = list(OLLAMA_CTX_CHOICES)
        self.ollama_ctx_slider = QSlider(Qt.Orientation.Horizontal)
        self.ollama_ctx_slider.setRange(0, len(self._ctx_choices) - 1)
        self.ollama_ctx_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.ollama_ctx_slider.setTickInterval(1)
        self.ollama_ctx_slider.setSingleStep(1)
        self.ollama_ctx_slider.setPageStep(1)
        self.ollama_ctx_slider.setFixedWidth(128)
        self.ollama_ctx_slider.setToolTip(
            "Ollama context length. Larger values use more VRAM; "
            "too small can truncate the prompt."
        )
        self.ollama_ctx_label = QLabel(format_ctx_label(self.settings.ollama_num_ctx))
        self.ollama_ctx_label.setMinimumWidth(36)
        self._set_ctx_slider_value(self.settings.ollama_num_ctx)
        self.ollama_ctx_slider.valueChanged.connect(self._on_ollama_ctx_changed)

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
        options_row.addWidget(self._inline_field("Ctx", self.ollama_ctx_slider))
        options_row.addWidget(self.ollama_ctx_label)
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
        self.export_pdf_button = QPushButton("Export PDF…")
        self.export_pdf_button.setEnabled(False)
        self.export_pdf_button.setToolTip(
            "Export a formatted meeting-notes PDF. Uses Ollama if no summary exists."
        )
        self.export_pdf_button.clicked.connect(self._export_pdf)
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
        action_row.addWidget(self.export_pdf_button)
        action_row.addWidget(self.export_button)
        root.addLayout(action_row)

        status_strip = QFrame()
        status_strip.setObjectName("statusStrip")
        status_layout = QHBoxLayout(status_strip)
        status_layout.setContentsMargins(8, 6, 8, 6)
        status_layout.setSpacing(10)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("jobProgressBar")
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setToolTip("Processing progress")
        self.progress_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self.stage_label = ElidedLabel("Ready")
        self.stage_label.setObjectName("jobStageLabel")
        self.stage_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.stage_label.setContentsMargins(12, 0, 12, 0)
        self.stage_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self.stage_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Ignored,
        )

        progress_host = QWidget()
        progress_host.setObjectName("jobProgressHost")
        progress_host.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        progress_stack = QGridLayout(progress_host)
        progress_stack.setContentsMargins(0, 0, 0, 0)
        progress_stack.setSpacing(0)
        progress_stack.addWidget(self.progress_bar, 0, 0)
        progress_stack.addWidget(self.stage_label, 0, 0)

        self.cpu_meter, self.cpu_bar, self.cpu_caption = self._build_status_meter(
            "CPU —",
            "cpuMeter",
        )
        self.ram_meter, self.ram_bar, self.ram_caption = self._build_status_meter(
            "RAM —",
            "ramMeter",
        )
        self.vram_meter, self.vram_bar, self.vram_caption = self._build_status_meter(
            "VRAM —",
            "vramMeter",
        )
        self.gpu_meter, self.gpu_bar, self.gpu_caption = self._build_status_meter(
            "GPU —",
            "gpuMeter",
        )
        self.elapsed_label = QLabel("Elapsed: 00:00")
        status_layout.addWidget(progress_host, 1)
        status_layout.addWidget(self.elapsed_label)
        status_layout.addWidget(self.cpu_meter)
        status_layout.addWidget(self.ram_meter)
        status_layout.addWidget(self.vram_meter)
        status_layout.addWidget(self.gpu_meter)
        root.addWidget(status_strip)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tabs = DetachableTabWidget()
        self.transcript_panel = TranscriptPanel()
        self.summary_view = QTextEdit()
        self.summary_view.setPlaceholderText("An optional local Ollama summary will appear here.")
        summary_font = QFont(self.summary_view.font())
        summary_font.setPointSize(12)
        self.summary_view.setFont(summary_font)
        self.summary_view.setAcceptRichText(True)
        self.summary_panel = SearchableTextPanel(
            self.summary_view,
            placeholder="Search summary…",
        )
        self.tabs.add_detachable_tab(
            self.transcript_panel,
            "Transcript",
            tab_id="transcript",
        )
        self.tabs.add_detachable_tab(self.summary_panel, "Summary", tab_id="summary")
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
        self._bind_find_shortcut()
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
    ) -> tuple[QWidget, QProgressBar, QLabel]:
        container = QWidget()
        container.setFixedWidth(118)
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
        bar.setFixedHeight(6)
        layout.addWidget(caption)
        layout.addWidget(bar)
        return container, bar, caption

    def _set_memory_meter(
        self,
        bar: QProgressBar,
        caption: QLabel,
        name: str,
        used_mb: int,
        total_mb: int,
    ) -> None:
        if total_mb <= 0:
            bar.setValue(0)
            caption.setText(f"{name} —")
            bar.setToolTip(f"{name} unavailable")
            return
        used_gb = used_mb / 1024
        total_gb = total_mb / 1024
        fraction = used_mb / total_mb
        bar.setValue(round(max(0.0, min(fraction, 1.0)) * 1000))
        caption.setText(f"{name} {used_gb:.1f} GB")
        bar.setToolTip(f"{name} {used_gb:.1f} / {total_gb:.1f} GB")

    def _set_percent_meter(
        self,
        bar: QProgressBar,
        caption: QLabel,
        name: str,
        percent: int | None,
        tooltip_noun: str,
    ) -> None:
        if percent is None:
            bar.setValue(0)
            caption.setText(f"{name} —")
            bar.setToolTip(f"{tooltip_noun} unavailable")
            return
        clamped = max(0, min(int(percent), 100))
        bar.setValue(clamped * 10)
        caption.setText(f"{name} {clamped}%")
        bar.setToolTip(f"{tooltip_noun} {clamped}%")

    def _set_vram_meter(self, used_mb: int, total_mb: int) -> None:
        self._set_memory_meter(
            self.vram_bar,
            self.vram_caption,
            "VRAM",
            used_mb,
            total_mb,
        )

    def _set_gpu_meter(self, percent: int | None) -> None:
        self._set_percent_meter(
            self.gpu_bar,
            self.gpu_caption,
            "GPU",
            percent,
            "GPU compute",
        )

    def _refresh_resource_meters(self) -> None:
        host = query_host_stats()
        self._set_percent_meter(
            self.cpu_bar,
            self.cpu_caption,
            "CPU",
            host.cpu_percent,
            "CPU",
        )
        self._set_memory_meter(
            self.ram_bar,
            self.ram_caption,
            "RAM",
            host.ram_used_mb,
            host.ram_total_mb,
        )
        stats = query_gpu_stats()
        if not stats.available:
            self._set_vram_meter(0, 0)
            self._set_gpu_meter(None)
            return
        self._set_vram_meter(stats.vram_used_mb, stats.vram_total_mb)
        self._set_gpu_meter(stats.gpu_util_percent)

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
        self._on_sources_changed()

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

    def _on_sources_changed(self) -> None:
        self._update_cache_controls()
        self._try_autoload_cached_transcript()

    def _source_key(self, sources: list[Path] | None) -> tuple[str, ...] | None:
        if not sources:
            return None
        return tuple(str(path.resolve()) for path in sources)

    def _displayed_source_key(self) -> tuple[str, ...] | None:
        if self.result is None:
            return None
        files = self.result.source_files or [self.result.source_file]
        return tuple(str(Path(path).resolve()) for path in files)

    def _try_autoload_cached_transcript(self) -> None:
        if self._autoload_in_progress:
            return
        if not self.settings.use_cached_transcript:
            return
        if self.worker is not None and self.worker.isRunning():
            return
        sources = self._current_sources()
        if sources is None:
            return
        if self._displayed_source_key() == self._source_key(sources):
            return
        cached = self.transcript_cache.load(sources)
        if cached is None:
            return
        self._autoload_in_progress = True
        try:
            self._load_from_cache(cached, sources)
        finally:
            self._autoload_in_progress = False

    def _update_cache_controls(self, extra_busy: bool = False) -> None:
        sources = self._current_sources()
        cache_available = sources is not None and self.transcript_cache.exists(sources)
        busy = extra_busy or (
            (self.worker is not None and self.worker.isRunning())
            or (self.summary_worker is not None and self.summary_worker.isRunning())
            or (self.pdf_export_worker is not None and self.pdf_export_worker.isRunning())
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

    def _persist_speaker_settings(self, *_args, save: bool = True) -> None:
        mode_index = self.speaker_mode.currentIndex()
        if 0 <= mode_index < len(SPEAKER_MODES):
            self.settings.speaker_mode = SPEAKER_MODES[mode_index]
        else:
            self.settings.speaker_mode = "automatic"
        self.settings.num_speakers = self.exact_speakers.value()
        self.settings.min_speakers = self.min_speakers.value()
        self.settings.max_speakers = self.max_speakers.value()
        if save:
            self.settings_store.save(self.settings)

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
        if self.settings.use_cached_transcript:
            cached = self.transcript_cache.load(sources)
            if cached is not None:
                if self._displayed_source_key() != self._source_key(sources):
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
        self.summary_markdown = ""
        self.progress_bar.setValue(1000)
        self.stage_label.setText(self._cache_status_message(result, sources))
        self.elapsed_label.setText("Elapsed: 00:00")
        self._refresh_resource_meters()
        self._show_result(sources)
        self._set_busy(False)
        self.notifications.show_message(
            self._cache_notification_message(result, sources),
            kind="info",
        )

    def _cache_notification_message(
        self,
        result: TranscriptResult,
        sources: list[Path],
    ) -> str:
        if len(sources) > 1:
            return f"Loaded cached transcript ({len(sources)} files)"
        name = Path(result.source_name or sources[0].name).name
        return f"Loaded cached transcript — {name}"

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
        self._persist_speaker_settings()
        self._clear_result_ui()
        self.progress_bar.setValue(0)
        self.started_at = time.monotonic()
        self.elapsed_timer.start(1000)
        self._set_busy(True)
        QApplication.processEvents()
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
            self._set_vram_meter(update.vram_used_mb, update.vram_total_mb)
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
        self.notifications.show_message("Transcription complete", kind="success")
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

    def _set_busy(
        self,
        busy: bool,
        summarizing: bool = False,
        exporting_pdf: bool = False,
    ) -> None:
        blocked = busy or summarizing or exporting_pdf
        self.start_button.setEnabled(not blocked)
        self.cancel_button.setEnabled(busy)
        self._update_cache_controls(blocked)
        has_result = self.result is not None
        self.export_button.setEnabled(not blocked and has_result)
        self.export_pdf_button.setEnabled(not blocked and has_result)
        ollama_ready = self.ollama_model_combo.has_selectable_model()
        self.summarize_button.setEnabled(
            not blocked and has_result and ollama_ready
        )
        self.refresh_ollama_button.setEnabled(not blocked)
        self.ollama_model_combo.setEnabled(not blocked and ollama_ready)
        self.ollama_ctx_slider.setEnabled(not blocked)
        if not blocked:
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

    def _clear_result_ui(self) -> None:
        self.result = None
        self._filtered_speaker = None
        self.summary_markdown = ""
        self.transcript_panel.clear()
        self.summary_view.clear()
        self.summary_panel.clear_search()
        self._populate_speaker_table()

    def _show_result(self, sources: list[Path] | None = None) -> None:
        self._apply_session_speaker_names(sources)
        self._filtered_speaker = None
        self.transcript_panel.set_speaker_filter(None)
        self.transcript_panel.set_result(self.result)
        self._populate_speaker_table()
        self.transcript_panel.highlight_speaker(None)
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

    def _bind_find_shortcut(self) -> None:
        shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(self._focus_current_tab_search)

    def _focus_current_tab_search(self) -> None:
        current = self.tabs.currentWidget()
        if current is self.transcript_panel:
            self.transcript_panel.focus_search()
        elif current is self.summary_panel:
            self.summary_panel.focus_search()

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
        filter_action = QAction(f"Filter by {label}", menu)
        filter_action.setCheckable(True)
        filter_action.setChecked(self._filtered_speaker == label)
        filter_action.setToolTip(
            "Show only this speaker's entries in the transcript"
        )
        menu.addAction(filter_action)
        menu.addSeparator()
        remove_action = menu.addAction(f"Remove {label} and their transcript entries")
        chosen = menu.exec(self.speaker_table.viewport().mapToGlobal(position))
        if chosen is filter_action:
            self._set_speaker_filter(label if filter_action.isChecked() else None)
        elif chosen is remove_action:
            self._remove_speaker(label)

    def _set_speaker_filter(self, speaker_id: str | None) -> None:
        self._filtered_speaker = speaker_id
        self.transcript_panel.set_speaker_filter(speaker_id)
        if speaker_id:
            self.tabs.ensure_visible(self.transcript_panel)
            self.transcript_panel.highlight_speaker(speaker_id)
            return
        self.transcript_panel.highlight_speaker(self._selected_speaker_label())

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
        if self._filtered_speaker == speaker_id:
            self._filtered_speaker = None
            self.transcript_panel.set_speaker_filter(None)
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
        self.transcript_panel.set_speaker_filter(self._filtered_speaker)
        self.transcript_panel.highlight_speaker(None)
        self.export_button.setEnabled(True)
        self.export_pdf_button.setEnabled(True)

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
        self._cap_ctx_slider_for_model()

    def _current_ollama_num_ctx(self) -> int:
        index = self.ollama_ctx_slider.value()
        if 0 <= index < len(self._ctx_choices):
            return self._ctx_choices[index]
        return snap_ollama_num_ctx(self.settings.ollama_num_ctx)

    def _set_ctx_slider_value(self, num_ctx: int) -> None:
        snapped = snap_ollama_num_ctx(num_ctx)
        if snapped not in self._ctx_choices:
            snapped = self._ctx_choices[-1]
        self.ollama_ctx_slider.blockSignals(True)
        self.ollama_ctx_slider.setValue(self._ctx_choices.index(snapped))
        self.ollama_ctx_slider.blockSignals(False)
        self.ollama_ctx_label.setText(format_ctx_label(snapped))

    def _on_ollama_ctx_changed(self, _value: int = 0) -> None:
        num_ctx = self._current_ollama_num_ctx()
        self.ollama_ctx_label.setText(format_ctx_label(num_ctx))
        if self.settings.ollama_num_ctx == num_ctx:
            return
        self.settings.ollama_num_ctx = num_ctx
        self.settings_store.save(self.settings)

    def _cap_ctx_slider_for_model(self) -> None:
        model_name = self.ollama_model_combo.current_model_name()
        max_ctx = None
        if model_name:
            try:
                max_ctx = RequirementsSummarizer.model_max_context(str(model_name))
            except Exception:
                max_ctx = None
        choices = [
            choice
            for choice in OLLAMA_CTX_CHOICES
            if max_ctx is None or choice <= max_ctx
        ]
        if not choices:
            choices = [OLLAMA_CTX_CHOICES[0]]
        current = self._current_ollama_num_ctx()
        self._ctx_choices = list(choices)
        self.ollama_ctx_slider.blockSignals(True)
        self.ollama_ctx_slider.setRange(0, len(self._ctx_choices) - 1)
        self.ollama_ctx_slider.blockSignals(False)
        preferred = current if current in self._ctx_choices else self._ctx_choices[-1]
        if self.settings.ollama_num_ctx in self._ctx_choices:
            preferred = self.settings.ollama_num_ctx
        self._set_ctx_slider_value(preferred)
        if self.settings.ollama_num_ctx != preferred:
            self.settings.ollama_num_ctx = preferred
            self.settings_store.save(self.settings)

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
        self._cap_ctx_slider_for_model()
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
            self.transcript_panel.set_speaker_filter(self._filtered_speaker)
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

    def _current_summary_markdown(self) -> str:
        markdown = self.summary_view.toMarkdown().strip()
        if is_usable_summary_markdown(markdown):
            return markdown
        plain = self.summary_view.toPlainText().strip()
        if is_usable_summary_markdown(plain):
            return plain
        stored = self.summary_markdown.strip()
        if is_usable_summary_markdown(stored):
            return stored
        return ""

    def _export_source_path(self) -> Path | None:
        if self.result is None:
            return None
        source = (
            self.result.source_files[0]
            if self.result.source_files
            else self.result.source_file
        )
        return Path(source) if source else None

    def _export_pdf(self) -> None:
        if self.result is None:
            return
        if self.pdf_export_worker and self.pdf_export_worker.isRunning():
            return
        if self.summary_worker and self.summary_worker.isRunning():
            return
        existing_markdown = self._current_summary_markdown()
        model_name = self.ollama_model_combo.current_model_name()
        if not existing_markdown and not model_name:
            QMessageBox.warning(
                self,
                "Ollama unavailable",
                "Select an available Ollama model before exporting a PDF "
                "without an existing summary.",
            )
            return
        source = self._export_source_path()
        initial_dir = self.settings.output_directory or str(
            (source.parent / "output") if source else Path.cwd()
        )
        stem = source.stem if source else "meeting"
        default_path = str(Path(initial_dir) / f"{stem}_meeting.pdf")
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Export meeting PDF",
            default_path,
            "PDF (*.pdf)",
        )
        if not destination:
            return
        path = Path(destination)
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")
        if model_name:
            self._persist_ollama_model_selection()
        self._pdf_streaming_summary = not bool(existing_markdown)
        if self._pdf_streaming_summary:
            self.summary_view.setPlainText("Generating summary…\n")
            self.tabs.ensure_visible(self.summary_view)
        self.progress_bar.setValue(0)
        self.started_at = time.monotonic()
        self.elapsed_timer.start(1000)
        self.stage_label.setText("Starting PDF export…")
        self._set_busy(False, exporting_pdf=True)
        self.pdf_export_worker = PdfExportWorker(
            str(path),
            render_text(self.result),
            existing_markdown,
            str(model_name or ""),
            self._current_ollama_num_ctx(),
            self,
        )
        self.pdf_export_worker.progress.connect(self._on_summary_progress)
        self.pdf_export_worker.chunk.connect(self._on_pdf_chunk)
        self.pdf_export_worker.section_break.connect(self._on_pdf_section_break)
        self.pdf_export_worker.summary_ready.connect(self._on_pdf_summary_ready)
        self.pdf_export_worker.completed.connect(self._pdf_export_completed)
        self.pdf_export_worker.failed.connect(self._pdf_export_failed)
        self.pdf_export_worker.start()

    def _on_pdf_chunk(self, text: str) -> None:
        if not self._pdf_streaming_summary:
            return
        self._on_summary_chunk(text)

    def _on_pdf_section_break(self) -> None:
        if not self._pdf_streaming_summary:
            return
        self._on_summary_section_break()

    def _on_pdf_summary_ready(self, text: str) -> None:
        self.summary_markdown = text.strip()
        if self.summary_markdown:
            self.summary_view.setMarkdown(self.summary_markdown)

    def _pdf_export_completed(self, destination: str) -> None:
        self._pdf_streaming_summary = False
        self.progress_bar.setValue(1000)
        self.stage_label.setText("PDF export complete")
        self._set_busy(False)
        QMessageBox.information(self, "PDF export complete", destination)

    def _pdf_export_failed(self, message: str) -> None:
        self._pdf_streaming_summary = False
        self.log_output.appendPlainText(f"PDF export failed: {message}")
        self.log_section.set_expanded(True)
        self.progress_bar.setValue(0)
        self.stage_label.setText("PDF export failed")
        self._set_busy(False)
        QMessageBox.critical(self, "PDF export failed", message)

    def _open_settings(self) -> None:
        try:
            SettingsDialog(self.settings, self.settings_store, self).exec()
        except Exception as exc:
            QMessageBox.critical(self, "Settings error", str(exc))

    def _summarize(self) -> None:
        if self.result is None or (
            self.summary_worker and self.summary_worker.isRunning()
        ) or (
            self.pdf_export_worker and self.pdf_export_worker.isRunning()
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
            self._current_ollama_num_ctx(),
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
            self.summary_markdown = text.strip()
            self.summary_view.setMarkdown(text)
        else:
            self.summary_markdown = ""
            self.summary_view.setPlainText(
                "Summary failed: Ollama returned an empty response. "
                "Try a non-reasoning model or click Summarize again."
            )
        self.progress_bar.setValue(1000)
        self.stage_label.setText("Summary complete" if text.strip() else "Summary failed")
        self._set_busy(False)

    def _summary_failed(self, message: str) -> None:
        self.summary_markdown = ""
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
        if self.pdf_export_worker and self.pdf_export_worker.isRunning():
            answer = QMessageBox.question(
                self,
                "PDF export is active",
                "Stop PDF export and close the application?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.pdf_export_worker.wait(5000)
        self.tabs.dock_all()
        self.settings.window_width = self.width()
        self.settings.window_height = self.height()
        self._persist_ollama_model_selection(save=False)
        self.settings.ollama_num_ctx = self._current_ollama_num_ctx()
        self._persist_speaker_settings(save=False)
        self.settings_store.save(self.settings)
        event.accept()
