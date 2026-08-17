"""The Prompt Lab window.

A separate top-level window rather than another tab in the main window: the lab
runs long batches, keeps its own model choices, and is not part of the normal
transcribe-and-summarize flow.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from speaker_transcriber.config import SettingsStore
from speaker_transcriber.promptlab.settings import LabSettingsStore
from speaker_transcriber.promptlab.store import LabStore
from speaker_transcriber.ui.oom_recovery_dialog import ask_gpu_recovery
from speaker_transcriber.ui.promptlab.ab_tab import ABTab
from speaker_transcriber.ui.promptlab.common import LabContext
from speaker_transcriber.ui.promptlab.judge_tab import JudgeTab
from speaker_transcriber.ui.promptlab.optimize_tab import OptimizeTab
from speaker_transcriber.ui.promptlab.prompts_tab import PromptsTab
from speaker_transcriber.ui.promptlab.runs_tab import RunsTab
from speaker_transcriber.ui.promptlab.transcripts_tab import TranscriptsTab
from speaker_transcriber.ui.promptlab.workers import (
    KIND_GENERATE,
    KIND_JUDGE,
    KIND_OPTIMIZE,
    KIND_SUMMARIZE,
    LabJob,
    LabJobRunner,
)
from speaker_transcriber.ui.worker import OllamaModelListWorker


LOGGER = logging.getLogger("speaker_transcriber.promptlab.window")


class PromptLabWindow(QMainWindow):
    def __init__(self, settings_store: SettingsStore | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Prompt Lab")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        store = LabStore()
        store.ensure()
        lab_settings_store = LabSettingsStore(store.root)
        settings = lab_settings_store.load()
        self._app_settings_store = settings_store or SettingsStore()
        app_settings = self._app_settings_store.load()
        settings.with_model_fallback(app_settings.ollama_model)
        lab_settings_store.save(settings)

        self.runner = LabJobRunner(self)
        self.context = LabContext(
            store,
            settings,
            lab_settings_store,
            self.runner,
            self._app_settings_store,
            self,
        )

        self.resize(settings.window_width, settings.window_height)
        self._build()
        self._connect_runner()
        self.context.status.connect(self._set_status)
        self._load_models()

        self.runner.start()

    def _build(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.transcripts_tab = TranscriptsTab(self.context)
        self.runs_tab = RunsTab(self.context)
        self.judge_tab = JudgeTab(self.context)
        self.ab_tab = ABTab(self.context)
        self.optimize_tab = OptimizeTab(self.context)
        self.prompts_tab = PromptsTab(self.context)
        self.tabs.addTab(self.transcripts_tab, "1. Transcripts")
        self.tabs.addTab(self.runs_tab, "2. Runs")
        self.tabs.addTab(self.judge_tab, "3. Judge")
        self.tabs.addTab(self.ab_tab, "4. A/B")
        self.tabs.addTab(self.optimize_tab, "5. Optimize")
        self.tabs.addTab(self.prompts_tab, "Prompts")
        layout.addWidget(self.tabs, 1)

        layout.addWidget(self._status_strip())
        self.setCentralWidget(central)

    def _status_strip(self) -> QWidget:
        strip = QWidget()
        row = QHBoxLayout(strip)
        row.setContentsMargins(8, 4, 8, 8)

        self.job_label = QLabel("Idle.")
        self.job_label.setMinimumWidth(360)
        row.addWidget(self.job_label, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setMaximumWidth(220)
        self.progress.setVisible(False)
        row.addWidget(self.progress)

        self.queue_label = QLabel("Queue: 0")
        row.addWidget(self.queue_label)

        self.cancel_button = QPushButton("Cancel all")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.runner.cancel_all)
        row.addWidget(self.cancel_button)

        self.refresh_models = QPushButton("Reload model list")
        self.refresh_models.clicked.connect(self._load_models)
        row.addWidget(self.refresh_models)
        return strip

    # Runner plumbing

    def _connect_runner(self) -> None:
        self.runner.job_started.connect(self._on_job_started)
        self.runner.job_progress.connect(self._on_job_progress)
        self.runner.job_finished.connect(self._on_job_finished)
        self.runner.job_failed.connect(self._on_job_failed)
        self.runner.job_cancelled.connect(self._on_job_cancelled)
        self.runner.queue_changed.connect(self._on_queue_changed)
        self.runner.idle.connect(self._on_idle)
        self.runner.oom_detected.connect(self._on_oom)

    def _on_job_started(self, job: LabJob) -> None:
        self.job_label.setText(job.label)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.cancel_button.setEnabled(True)

    def _on_job_progress(self, job_id: str, fraction: float, message: str) -> None:
        self.progress.setValue(int(fraction * 100))
        if message:
            self.job_label.setText(message)

    def _on_job_finished(self, job_id: str, kind: str, result: object) -> None:
        if kind == KIND_GENERATE:
            self.context.transcripts_changed.emit()
        elif kind == KIND_SUMMARIZE:
            self.context.runs_changed.emit()
        elif kind == KIND_JUDGE:
            self.context.scores_changed.emit()
        elif kind == KIND_OPTIMIZE:
            self.optimize_tab.show_candidate(result)  # type: ignore[arg-type]

    def _on_job_failed(self, job_id: str, message: str) -> None:
        job = self._find_job(job_id)
        label = job.label if job else "A Prompt Lab job"
        LOGGER.error("%s failed: %s", label, message)
        self.job_label.setText(f"Failed: {label}")
        QMessageBox.warning(self, "Job failed", f"{label}\n\n{message}")

    def _on_job_cancelled(self, job_id: str) -> None:
        self.job_label.setText("Cancelled.")

    def _on_queue_changed(self, depth: int) -> None:
        self.queue_label.setText(f"Queue: {depth}")
        self.cancel_button.setEnabled(depth > 0)

    def _on_idle(self) -> None:
        self.job_label.setText("Idle.")
        self.progress.setVisible(False)

    def _on_oom(self, request: object) -> None:
        choice = ask_gpu_recovery(request, self)  # type: ignore[arg-type]
        self.runner.provide_recovery(choice)

    def _find_job(self, job_id: str) -> LabJob | None:
        current = self.runner.current_job
        if current is not None and current.job_id == job_id:
            return current
        return next(
            (job for job in self.runner.pending_jobs() if job.job_id == job_id), None
        )

    def _set_status(self, message: str) -> None:
        self.job_label.setText(message)

    # Models

    def _load_models(self) -> None:
        self.refresh_models.setEnabled(False)
        self._model_worker = OllamaModelListWorker(self)
        self._model_worker.completed.connect(self._on_models)
        self._model_worker.failed.connect(self._on_models_failed)
        self._model_worker.start()

    def _on_models(self, models: list) -> None:
        self.refresh_models.setEnabled(True)
        self.context.set_models([model.name for model in models])

    def _on_models_failed(self, message: str) -> None:
        self.refresh_models.setEnabled(True)
        self.job_label.setText(
            "Could not reach Ollama; type a model name manually. " + message
        )

    # Lifecycle

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.transcripts_tab.tts.shutdown()
        self.context.settings.window_width = self.width()
        self.context.settings.window_height = self.height()
        self.context.save_settings()
        self.runner.stop()
        self.runner.wait(3000)
        super().closeEvent(event)
