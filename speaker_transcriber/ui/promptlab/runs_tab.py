"""Summarize transcripts under one or more prompt variants."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from speaker_transcriber.promptlab.promptset import list_variants
from speaker_transcriber.promptlab.summarize_runner import RunSettings, run_summary
from speaker_transcriber.promptlab.types import (
    GeneratedTranscript,
    PromptVariant,
    SummaryRun,
    new_id,
)
from speaker_transcriber.ui.promptlab.common import (
    LabContext,
    MarkdownView,
    ctx_combo,
    current_id,
    elide,
    fill_models,
    heading,
    hint,
    make_table,
    model_combo,
    selected_ids,
    set_row,
    style_combo,
)
from speaker_transcriber.ui.promptlab.workers import KIND_SUMMARIZE, JobContext, LabJob


class RunsTab(QWidget):
    def __init__(self, context: LabContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._build()
        self.context.models_changed.connect(self._on_models)
        self.context.transcripts_changed.connect(self.refresh)
        self.context.runs_changed.connect(self._refresh_runs)
        self.context.variants_changed.connect(self._refresh_variants)
        self.refresh()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._controls(), 0)

        splitter = QSplitter(Qt.Orientation.Vertical)

        upper = QSplitter(Qt.Orientation.Horizontal)
        transcripts = QWidget()
        transcripts_column = QVBoxLayout(transcripts)
        transcripts_column.setContentsMargins(0, 0, 0, 0)
        transcripts_column.addWidget(heading("Transcripts"))
        self.transcript_table = make_table(
            ["Label", "Mode", "Words", "Runs"], multi_select=True
        )
        transcripts_column.addWidget(self.transcript_table)
        upper.addWidget(transcripts)

        variants = QWidget()
        variants_column = QVBoxLayout(variants)
        variants_column.setContentsMargins(0, 0, 0, 0)
        variants_column.addWidget(heading("Prompt variants"))
        self.variant_list = QListWidget()
        self.variant_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        variants_column.addWidget(self.variant_list)
        upper.addWidget(variants)
        upper.setSizes([520, 380])
        splitter.addWidget(upper)

        lower = QSplitter(Qt.Orientation.Horizontal)
        runs = QWidget()
        runs_column = QVBoxLayout(runs)
        runs_column.setContentsMargins(0, 0, 0, 0)
        runs_column.addWidget(heading("Runs"))
        self.run_table = make_table(
            ["Transcript", "Variant", "Words", "Seconds", "Status"], multi_select=True
        )
        self.run_table.itemSelectionChanged.connect(self._show_run)
        runs_column.addWidget(self.run_table)
        lower.addWidget(runs)

        self.preview = MarkdownView()
        lower.addWidget(self.preview)
        lower.setSizes([520, 520])
        splitter.addWidget(lower)
        splitter.setSizes([300, 460])
        layout.addWidget(splitter, 1)

    def _controls(self) -> QWidget:
        settings = self.context.settings
        panel = QWidget()
        panel.setMaximumWidth(320)
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 8, 0)

        box = QGroupBox("Summarizer under test")
        form = QFormLayout(box)
        self.style_selector = style_combo(settings.style_id)
        self.style_selector.currentIndexChanged.connect(self._on_style)
        form.addRow("Style", self.style_selector)
        self.model = model_combo(settings.summarizer_model)
        form.addRow("Model", self.model)
        self.num_ctx = ctx_combo(settings.summarizer_num_ctx)
        form.addRow("Context", self.num_ctx)
        self.omit_names = QCheckBox("Omit speaker attribution")
        form.addRow("", self.omit_names)
        column.addWidget(box)

        column.addWidget(
            hint(
                "A run is one transcript summarized by one variant. Selecting "
                "several of each queues the whole matrix, one job at a time."
            )
        )

        self.run_selected = QPushButton("Run selected matrix")
        self.run_selected.clicked.connect(self._run_selected)
        column.addWidget(self.run_selected)

        self.run_missing = QPushButton("Run only what is missing")
        self.run_missing.clicked.connect(lambda: self._run_selected(skip_existing=True))
        column.addWidget(self.run_missing)

        column.addWidget(heading("Selected runs"))
        self.delete_button = QPushButton("Delete runs")
        self.delete_button.clicked.connect(self._delete_runs)
        column.addWidget(self.delete_button)

        column.addStretch()
        return panel

    # Data

    @property
    def style_id(self) -> str:
        return str(self.style_selector.currentData())

    def _on_style(self) -> None:
        self.context.settings.style_id = self.style_id
        self.context.save_settings()
        self.refresh()

    def _on_models(self, names: list[str]) -> None:
        fill_models(self.model, names, self.context.settings.summarizer_model)

    def refresh(self) -> None:
        self._refresh_variants()
        self._refresh_transcripts()
        self._refresh_runs()

    def _refresh_variants(self) -> None:
        chosen = {
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.variant_list.selectedItems()
        }
        self.variant_list.clear()
        for variant in list_variants(self.context.store, self.style_id):
            stages = ", ".join(variant.overridden_stages) or "all stages as shipped"
            item = QListWidgetItem(f"{variant.label}  —  {stages}")
            item.setData(Qt.ItemDataRole.UserRole, variant.variant_id)
            item.setToolTip(variant.rationale or variant.variant_id)
            self.variant_list.addItem(item)
            if variant.variant_id in chosen:
                item.setSelected(True)
        if not self.variant_list.selectedItems() and self.variant_list.count():
            self.variant_list.item(0).setSelected(True)

    def _refresh_transcripts(self) -> None:
        transcripts = sorted(
            self.context.store.transcripts.all(),
            key=lambda item: item.created_at,
            reverse=True,
        )
        counts: dict[str, int] = {}
        for run in self.context.store.runs.all():
            counts[run.transcript_id] = counts.get(run.transcript_id, 0) + 1
        self.transcript_table.setRowCount(len(transcripts))
        for row, transcript in enumerate(transcripts):
            set_row(
                self.transcript_table,
                row,
                [
                    elide(transcript.label or transcript.transcript_id, 46),
                    transcript.mode,
                    f"{transcript.word_count:,}",
                    str(counts.get(transcript.transcript_id, 0)),
                ],
                identifier=transcript.transcript_id,
            )

    def _refresh_runs(self) -> None:
        runs = sorted(
            (
                run
                for run in self.context.store.runs.all()
                if run.style_id == self.style_id
            ),
            key=lambda item: item.created_at,
            reverse=True,
        )
        labels = {
            transcript.transcript_id: transcript.label
            for transcript in self.context.store.transcripts.all()
        }
        self.run_table.setRowCount(len(runs))
        for row, run in enumerate(runs):
            status = "ok" if run.succeeded else (run.error or "empty")
            set_row(
                self.run_table,
                row,
                [
                    elide(labels.get(run.transcript_id, run.transcript_id), 40),
                    run.variant_id,
                    f"{len(run.markdown.split()):,}",
                    f"{run.elapsed_seconds:.0f}",
                    elide(status, 40),
                ],
                identifier=run.run_id,
                tooltip=run.error,
            )

    def _show_run(self) -> None:
        run_id = current_id(self.run_table)
        if not run_id:
            return
        run = self.context.store.runs.get(run_id)
        if run is None:
            return
        if run.succeeded:
            self.preview.show_markdown(run.markdown)
        else:
            self.preview.show_plain(run.error or "This run produced no notes.")

    # Actions

    def _selected_variants(self) -> list[PromptVariant]:
        chosen = {
            str(item.data(Qt.ItemDataRole.UserRole))
            for item in self.variant_list.selectedItems()
        }
        return [
            variant
            for variant in list_variants(self.context.store, self.style_id)
            if variant.variant_id in chosen
        ]

    def _selected_transcripts(self) -> list[GeneratedTranscript]:
        chosen = selected_ids(self.transcript_table)
        found = []
        for transcript_id in chosen:
            transcript = self.context.store.transcripts.get(transcript_id)
            if transcript is not None:
                found.append(transcript)
        return found

    def _run_selected(self, skip_existing: bool = False) -> None:
        transcripts = self._selected_transcripts()
        variants = self._selected_variants()
        if not transcripts or not variants:
            QMessageBox.information(
                self,
                "Nothing selected",
                "Select at least one transcript and one prompt variant.",
            )
            return

        settings = self.context.settings
        settings.summarizer_model = self.model.currentText().strip()
        settings.summarizer_num_ctx = int(self.num_ctx.currentData())
        self.context.save_settings()
        if not settings.summarizer_model:
            QMessageBox.warning(
                self,
                "No model",
                "Choose the Ollama model the summarizer should use.",
            )
            return

        existing = {
            (run.transcript_id, run.variant_id)
            for run in self.context.store.runs.all()
            if run.succeeded
        }
        run_settings = RunSettings(
            model_name=settings.summarizer_model,
            num_ctx=settings.summarizer_num_ctx,
            omit_speaker_names=self.omit_names.isChecked(),
        )

        queued = 0
        for transcript in transcripts:
            for variant in variants:
                if skip_existing and (transcript.transcript_id, variant.variant_id) in existing:
                    continue
                self.context.runner.enqueue(
                    LabJob(
                        job_id=new_id("job"),
                        kind=KIND_SUMMARIZE,
                        label=f"Summarize «{elide(transcript.label, 40)}» with {variant.label}",
                        model_name=run_settings.model_name,
                        num_ctx=run_settings.num_ctx,
                        run=_summarize_job(self.context, transcript, variant, run_settings),
                        payload={
                            "transcript_id": transcript.transcript_id,
                            "variant_id": variant.variant_id,
                        },
                    )
                )
                queued += 1
        self.context.status.emit(
            f"Queued {queued} run(s) across {len(transcripts)} transcript(s) "
            f"and {len(variants)} variant(s)."
        )

    def _delete_runs(self) -> None:
        chosen = selected_ids(self.run_table)
        if not chosen:
            return
        for run_id in chosen:
            self.context.store.runs.delete(run_id)
            self.context.store.scores.delete(run_id)
        self.context.runs_changed.emit()
        self.context.scores_changed.emit()


def _summarize_job(
    context: LabContext,
    transcript: GeneratedTranscript,
    variant: PromptVariant,
    settings: RunSettings,
):
    def run(job_context: JobContext) -> SummaryRun:
        summary = run_summary(
            transcript,
            variant,
            RunSettings(
                model_name=job_context.model_name,
                num_ctx=job_context.num_ctx,
                excluded_sections=settings.excluded_sections,
                omit_speaker_names=settings.omit_speaker_names,
            ),
            on_progress=job_context.progress,
            cancel_event=job_context.cancel_event,
        )
        context.store.runs.save(summary)
        return summary

    return run
