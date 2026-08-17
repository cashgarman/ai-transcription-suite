"""Generate synthetic transcripts, singly or in batches."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from speaker_transcriber.promptlab.generator import (
    GenerationSettings,
    generate_transcript,
)
from speaker_transcriber.promptlab.scenarios import (
    MEETING_KINDS,
    build_freeform_scenario,
    build_scenario,
    suggested_style,
)
from speaker_transcriber.promptlab.transcript_build import result_from_payload
from speaker_transcriber.promptlab.types import (
    DISFLUENCY_LEVELS,
    FREEFORM_MODE,
    GROUNDED_MODE,
    GeneratedTranscript,
    Scenario,
    new_id,
)
from speaker_transcriber.ui.promptlab.common import (
    LabContext,
    MarkdownView,
    ctx_combo,
    current_id,
    fill_models,
    heading,
    hint,
    make_table,
    model_combo,
    selected_ids,
    set_row,
    style_combo,
)
from speaker_transcriber.ui.promptlab.workers import KIND_GENERATE, JobContext, LabJob
from speaker_transcriber.ui.transcript_tts_controller import (
    TranscriptTtsController,
    bind_transcript_playback_follow,
)
from speaker_transcriber.ui.transcript_view import TranscriptView


MODE_LABELS = {
    GROUNDED_MODE: "Grounded (known ground truth)",
    FREEFORM_MODE: "Free-form (no answer key)",
}

DISFLUENCY_LABELS = {
    "clean": "Clean — tidy sentences",
    "light": "Light — natural speech",
    "heavy": "Heavy — messy, overlapping, mis-heard words",
}


class TranscriptsTab(QWidget):
    def __init__(self, context: LabContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._build()
        self.context.models_changed.connect(self._on_models)
        self.context.transcripts_changed.connect(self.refresh)
        self.refresh()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.tts = TranscriptTtsController(
            settings_store=self.context.app_settings_store,
            include_voice_model=False,
        )
        self.tts_bar = self.tts.bar

        layout.addWidget(self._controls(), 0)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.table = make_table(
            ["Label", "Mode", "Style", "Words", "Seed", "Created"], multi_select=True
        )
        self.table.itemSelectionChanged.connect(self._show_selected)
        splitter.addWidget(self.table)

        self.detail = QTabWidget()
        transcript_page = QWidget()
        transcript_layout = QVBoxLayout(transcript_page)
        transcript_layout.setContentsMargins(0, 0, 0, 0)
        transcript_layout.setSpacing(6)
        transcript_layout.addWidget(self.tts)
        self.transcript_view = TranscriptView()
        self.transcript_view.setReadOnly(True)
        transcript_layout.addWidget(self.transcript_view, 1)
        bind_transcript_playback_follow(self.tts, self.transcript_view)
        self.truth_view = MarkdownView()
        self.detail.addTab(transcript_page, "Transcript")
        self.detail.addTab(self.truth_view, "Ground truth")
        splitter.addWidget(self.detail)
        splitter.setSizes([260, 460])
        layout.addWidget(splitter, 1)

    def _controls(self) -> QWidget:
        settings = self.context.settings
        panel = QWidget()
        panel.setMaximumWidth(360)
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 8, 0)

        box = QGroupBox("Scenario")
        form = QFormLayout(box)

        self.mode_combo = QComboBox()
        for mode, label in MODE_LABELS.items():
            self.mode_combo.addItem(label, mode)
        index = self.mode_combo.findData(settings.generation_mode)
        self.mode_combo.setCurrentIndex(max(0, index))
        self.mode_combo.currentIndexChanged.connect(self._on_mode)
        form.addRow("Mode", self.mode_combo)

        self.kind_combo = QComboBox()
        for kind in MEETING_KINDS:
            self.kind_combo.addItem(kind.label, kind.kind_id)
        kind_index = self.kind_combo.findData(settings.meeting_kind)
        self.kind_combo.setCurrentIndex(max(0, kind_index))
        self.kind_combo.currentIndexChanged.connect(self._on_kind)
        form.addRow("Meeting kind", self.kind_combo)

        self.random_kind = QCheckBox("Vary the kind across a batch")
        self.random_kind.setChecked(settings.random_kind)
        form.addRow("", self.random_kind)

        self.style_selector = style_combo(settings.style_id)
        form.addRow("Summary style", self.style_selector)

        self.duration = QSpinBox()
        self.duration.setRange(5, 180)
        self.duration.setSingleStep(5)
        self.duration.setSuffix(" min")
        self.duration.setValue(settings.duration_minutes)
        form.addRow("Meeting length", self.duration)

        self.disfluency = QComboBox()
        for level in DISFLUENCY_LEVELS:
            self.disfluency.addItem(DISFLUENCY_LABELS[level], level)
        dis_index = self.disfluency.findData(settings.disfluency)
        self.disfluency.setCurrentIndex(max(0, dis_index))
        form.addRow("Speech", self.disfluency)

        self.seed = QSpinBox()
        self.seed.setRange(0, 2_000_000_000)
        self.seed.setValue(settings.base_seed)
        form.addRow("Base seed", self.seed)

        self.count = QSpinBox()
        self.count.setRange(1, 64)
        self.count.setValue(settings.batch_size)
        form.addRow("Batch size", self.count)
        column.addWidget(box)

        model_box = QGroupBox("Generator model")
        model_form = QFormLayout(model_box)
        self.model = model_combo(settings.generator_model)
        model_form.addRow("Model", self.model)
        self.num_ctx = ctx_combo(settings.generator_num_ctx)
        model_form.addRow("Context", self.num_ctx)
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.05)
        self.temperature.setValue(settings.generator_temperature)
        model_form.addRow("Temperature", self.temperature)
        column.addWidget(model_box)

        voice_box = QGroupBox("Playback voice")
        voice_form = QFormLayout(voice_box)
        voice_form.addRow("Voice model", self.tts_bar.model_combo)
        column.addWidget(voice_box)

        column.addWidget(
            hint(
                "Seeds are consecutive from the base seed, so a batch is "
                "reproducible: the same base seed and batch size always plan "
                "the same meetings."
            )
        )

        buttons = QVBoxLayout()
        self.preview_button = QPushButton("Preview scenario")
        self.preview_button.clicked.connect(self._preview)
        buttons.addWidget(self.preview_button)

        self.generate_one = QPushButton("Generate one")
        self.generate_one.clicked.connect(lambda: self._generate(1))
        buttons.addWidget(self.generate_one)

        self.generate_batch = QPushButton("Generate batch")
        self.generate_batch.clicked.connect(lambda: self._generate(self.count.value()))
        buttons.addWidget(self.generate_batch)
        column.addLayout(buttons)

        column.addWidget(heading("Selected transcripts"))
        actions = QHBoxLayout()
        self.export_button = QPushButton("Export JSON…")
        self.export_button.clicked.connect(self._export)
        actions.addWidget(self.export_button)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._delete)
        actions.addWidget(self.delete_button)
        column.addLayout(actions)

        column.addStretch()
        return panel

    # Settings plumbing

    def _on_mode(self) -> None:
        grounded = self.mode_combo.currentData() == GROUNDED_MODE
        self.detail.setTabEnabled(1, grounded)

    def _on_kind(self) -> None:
        self.style_selector.setCurrentIndex(
            max(
                0,
                self.style_selector.findData(
                    suggested_style(self.kind_combo.currentData())
                ),
            )
        )

    def _on_models(self, names: list[str]) -> None:
        fill_models(self.model, names, self.context.settings.generator_model)

    def _capture_settings(self) -> None:
        settings = self.context.settings
        settings.generation_mode = str(self.mode_combo.currentData())
        settings.meeting_kind = str(self.kind_combo.currentData())
        settings.random_kind = self.random_kind.isChecked()
        settings.style_id = str(self.style_selector.currentData())
        settings.duration_minutes = self.duration.value()
        settings.disfluency = str(self.disfluency.currentData())
        settings.base_seed = self.seed.value()
        settings.batch_size = self.count.value()
        settings.generator_model = self.model.currentText().strip()
        settings.generator_num_ctx = int(self.num_ctx.currentData())
        settings.generator_temperature = self.temperature.value()
        self.context.save_settings()

    def _make_scenario(self, seed: int, *, vary_kind: bool) -> Scenario:
        mode = str(self.mode_combo.currentData())
        kind = None if vary_kind and self.random_kind.isChecked() else str(
            self.kind_combo.currentData()
        )
        builder = build_scenario if mode == GROUNDED_MODE else build_freeform_scenario
        return builder(
            seed,
            kind_id=kind,
            style_id=str(self.style_selector.currentData()),
            duration_minutes=self.duration.value(),
            disfluency=str(self.disfluency.currentData()),
        )

    # Actions

    def _preview(self) -> None:
        scenario = self._make_scenario(self.seed.value(), vary_kind=False)
        self.truth_view.show_markdown(_scenario_markdown(scenario))
        self.detail.setCurrentIndex(1)
        self.context.status.emit(
            f"Previewed scenario for seed {scenario.seed}: "
            f"{len(scenario.facts)} facts, {len(scenario.distractors)} distractors."
        )

    def _generate(self, count: int) -> None:
        self._capture_settings()
        settings = self.context.settings
        if not settings.generator_model:
            QMessageBox.warning(
                self,
                "No generator model",
                "Choose an Ollama model to write the dialogue.",
            )
            return

        base = settings.base_seed
        for offset in range(count):
            scenario = self._make_scenario(base + offset, vary_kind=count > 1)
            self.context.store.scenarios.save(scenario)
            generation = GenerationSettings(
                model_name=settings.generator_model,
                num_ctx=settings.generator_num_ctx,
                temperature=settings.generator_temperature,
            )
            self.context.runner.enqueue(
                LabJob(
                    job_id=new_id("job"),
                    kind=KIND_GENERATE,
                    label=f"Generate «{scenario.title}» (seed {scenario.seed})",
                    model_name=generation.model_name,
                    num_ctx=generation.num_ctx,
                    run=_generate_job(self.context, scenario, generation),
                    payload={"scenario_id": scenario.scenario_id},
                )
            )
        self.context.status.emit(f"Queued {count} transcript(s) for generation.")

    def _export(self) -> None:
        chosen = selected_ids(self.table)
        if not chosen:
            return
        directory = QFileDialog.getExistingDirectory(self, "Export transcripts to…")
        if not directory:
            return
        from pathlib import Path

        written = 0
        for transcript_id in chosen:
            transcript = self.context.store.transcripts.get(transcript_id)
            if transcript is None:
                continue
            path = Path(directory) / f"{transcript_id}.json"
            path.write_text(
                json.dumps(transcript.transcript, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            written += 1
        self.context.status.emit(f"Exported {written} transcript(s) to {directory}.")

    def _delete(self) -> None:
        chosen = selected_ids(self.table)
        if not chosen:
            return
        answer = QMessageBox.question(
            self,
            "Delete transcripts",
            f"Delete {len(chosen)} transcript(s)? Runs already recorded against "
            "them are kept.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        for transcript_id in chosen:
            self.context.store.transcripts.delete(transcript_id)
        self.context.transcripts_changed.emit()

    # Rendering

    def refresh(self) -> None:
        transcripts = sorted(
            self.context.store.transcripts.all(),
            key=lambda item: item.created_at,
            reverse=True,
        )
        self.table.setRowCount(len(transcripts))
        for row, transcript in enumerate(transcripts):
            set_row(
                self.table,
                row,
                [
                    transcript.label or transcript.transcript_id,
                    "grounded" if transcript.mode == GROUNDED_MODE else "free-form",
                    transcript.style_id,
                    f"{transcript.word_count:,}",
                    str(transcript.seed),
                    transcript.created_at.replace("T", " ")[:16],
                ],
                identifier=transcript.transcript_id,
            )
        if transcripts and self.table.currentRow() < 0:
            self.table.selectRow(0)
        elif not transcripts:
            self._clear_detail()

    def _clear_detail(self) -> None:
        self.transcript_view.set_result(None)
        self.truth_view.show_markdown("")
        self.tts.set_result(None)

    def _show_selected(self) -> None:
        transcript_id = current_id(self.table)
        if not transcript_id:
            self._clear_detail()
            return
        transcript = self.context.store.transcripts.get(transcript_id)
        if transcript is None:
            self._clear_detail()
            return
        try:
            result = result_from_payload(transcript.transcript)
        except (KeyError, TypeError, ValueError):
            result = None
        self.transcript_view.set_result(result)
        self.tts.set_result(result)
        scenario = self.context.store.scenarios.get(transcript.scenario_id)
        self.truth_view.show_markdown(
            _scenario_markdown(scenario)
            if scenario is not None
            else "This transcript has no stored scenario."
        )


def _scenario_markdown(scenario: Scenario) -> str:
    lines = [
        f"# {scenario.title}",
        "",
        f"Seed {scenario.seed} · {scenario.meeting_kind.replace('_', ' ')} · "
        f"{scenario.duration_minutes} minutes · {scenario.disfluency} speech",
        "",
        "## Participants",
        "",
    ]
    for person in scenario.participants:
        lines.append(
            f"- **{person.name}** ({person.role}) — {person.speaking_style}"
        )
    lines.extend(["", "## Topics", ""])
    for topic in scenario.topics:
        lines.append(f"- **{topic.title}** — {topic.intent}")

    if not scenario.facts:
        lines.extend(
            [
                "",
                "## Ground truth",
                "",
                "This is a free-form scenario. There is no answer key, so the "
                "judge grades it against the transcript itself.",
            ]
        )
        return "\n".join(lines)

    lines.extend(["", "## Facts the notes must carry", ""])
    for fact in scenario.facts:
        owner = f" — owner: {fact.owner}" if fact.owner else ""
        lines.append(
            f"- `{fact.fact_id}` **{fact.kind}** ({fact.salience}): {fact.text}{owner}"
        )
    if scenario.distractors:
        lines.extend(["", "## Raised and dropped (must not be reported as real)", ""])
        for item in scenario.distractors:
            lines.append(f"- `{item.distractor_id}` ({item.reason}): {item.text}")
    return "\n".join(lines)


def _generate_job(context: LabContext, scenario: Scenario, settings: GenerationSettings):
    def run(job_context: JobContext) -> GeneratedTranscript:
        transcript = generate_transcript(
            scenario,
            GenerationSettings(
                model_name=job_context.model_name,
                num_ctx=job_context.num_ctx,
                temperature=settings.temperature,
            ),
            on_progress=job_context.progress,
            cancel_event=job_context.cancel_event,
        )
        context.store.transcripts.save(transcript)
        return transcript

    return run
