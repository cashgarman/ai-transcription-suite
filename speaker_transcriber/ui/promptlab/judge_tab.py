"""Score runs with the deterministic checks and the local judge model."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from speaker_transcriber.promptlab.judge import JudgeSettings, judge_run
from speaker_transcriber.promptlab.types import (
    GROUNDED_MODE,
    STATUS_COVERED,
    STATUS_MISSING,
    Scorecard,
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
    score_text,
    selected_ids,
    set_row,
)
from speaker_transcriber.ui.promptlab.workers import KIND_JUDGE, JobContext, LabJob


STATUS_MARK = {STATUS_COVERED: "covered", "partial": "partial", STATUS_MISSING: "MISSING"}


class JudgeTab(QWidget):
    def __init__(self, context: LabContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._build()
        self.context.models_changed.connect(self._on_models)
        self.context.runs_changed.connect(self.refresh)
        self.context.scores_changed.connect(self.refresh)
        self.refresh()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._controls(), 0)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.table = make_table(
            [
                "Transcript",
                "Variant",
                "Mode",
                "Recall",
                "Precision",
                "Rubric",
                "Structure",
                "Composite",
            ],
            multi_select=True,
        )
        self.table.itemSelectionChanged.connect(self._show_detail)
        splitter.addWidget(self.table)

        self.detail = MarkdownView()
        splitter.addWidget(self.detail)
        splitter.setSizes([340, 420])
        layout.addWidget(splitter, 1)

    def _controls(self) -> QWidget:
        settings = self.context.settings
        panel = QWidget()
        panel.setMaximumWidth(320)
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 8, 0)

        box = QGroupBox("Judge model")
        form = QFormLayout(box)
        self.model = model_combo(settings.judge_model)
        form.addRow("Model", self.model)
        self.num_ctx = ctx_combo(settings.judge_num_ctx)
        form.addRow("Context", self.num_ctx)
        column.addWidget(box)

        column.addWidget(
            hint(
                "Grounded transcripts are graded fact by fact against their "
                "answer key. Free-form ones are graded against the transcript "
                "itself, so they get no recall score. Structure, headings, and "
                "table checks run without a model either way."
            )
        )

        self.judge_selected = QPushButton("Judge selected runs")
        self.judge_selected.clicked.connect(self._judge_selected)
        column.addWidget(self.judge_selected)

        self.judge_unjudged = QPushButton("Judge everything unjudged")
        self.judge_unjudged.clicked.connect(self._judge_unjudged)
        column.addWidget(self.judge_unjudged)

        self.rejudge = QPushButton("Re-judge selected")
        self.rejudge.clicked.connect(lambda: self._judge_selected(force=True))
        column.addWidget(self.rejudge)

        column.addStretch()
        return panel

    def _on_models(self, names: list[str]) -> None:
        fill_models(self.model, names, self.context.settings.judge_model)

    # Data

    def refresh(self) -> None:
        runs = {run.run_id: run for run in self.context.store.runs.all()}
        labels = {
            transcript.transcript_id: transcript.label
            for transcript in self.context.store.transcripts.all()
        }
        cards = sorted(
            self.context.store.scores.all(),
            key=lambda card: card.created_at,
            reverse=True,
        )
        self.table.setRowCount(len(cards))
        for row, card in enumerate(cards):
            run = runs.get(card.run_id)
            transcript_label = labels.get(card.transcript_id, card.transcript_id)
            set_row(
                self.table,
                row,
                [
                    elide(transcript_label, 36),
                    card.variant_id,
                    card.mode,
                    score_text(card.recall),
                    score_text(card.precision),
                    f"{card.rubric.mean:.1f}" if card.rubric.mean else "—",
                    f"{card.structure.score:.2f}",
                    score_text(card.composite) if not card.error else "failed",
                ],
                identifier=card.run_id,
                tooltip=card.error or (run.error if run else ""),
            )
        if cards and self.table.currentRow() < 0:
            self.table.selectRow(0)

    def _show_detail(self) -> None:
        run_id = current_id(self.table)
        if not run_id:
            return
        card = self.context.store.scores.get(run_id)
        if card is None:
            return
        run = self.context.store.runs.get(run_id)
        scenario = None
        if run is not None and run.scenario_id:
            scenario = self.context.store.scenarios.get(run.scenario_id)
        self.detail.show_markdown(_scorecard_markdown(card, scenario))

    # Actions

    def _capture(self) -> JudgeSettings | None:
        settings = self.context.settings
        settings.judge_model = self.model.currentText().strip()
        settings.judge_num_ctx = int(self.num_ctx.currentData())
        self.context.save_settings()
        if not settings.judge_model:
            QMessageBox.warning(
                self, "No judge model", "Choose an Ollama model to grade the notes."
            )
            return None
        return JudgeSettings(
            model_name=settings.judge_model, num_ctx=settings.judge_num_ctx
        )

    def _queue(self, runs: list[SummaryRun]) -> None:
        settings = self._capture()
        if settings is None:
            return
        labels = {
            transcript.transcript_id: transcript.label
            for transcript in self.context.store.transcripts.all()
        }
        queued = 0
        for run in runs:
            transcript = self.context.store.transcripts.get(run.transcript_id)
            if transcript is None:
                continue
            scenario = (
                self.context.store.scenarios.get(run.scenario_id)
                if run.scenario_id
                else None
            )
            self.context.runner.enqueue(
                LabJob(
                    job_id=new_id("job"),
                    kind=KIND_JUDGE,
                    label=f"Judge {run.variant_id} on «{elide(labels.get(run.transcript_id, ''), 34)}»",
                    model_name=settings.model_name,
                    num_ctx=settings.num_ctx,
                    run=_judge_job(self.context, run, transcript, scenario, settings),
                    payload={"run_id": run.run_id},
                )
            )
            queued += 1
        self.context.status.emit(f"Queued {queued} run(s) for judging.")

    def _judge_selected(self, force: bool = False) -> None:
        chosen = selected_ids(self.table)
        if chosen:
            runs = [
                run
                for run in (self.context.store.runs.get(run_id) for run_id in chosen)
                if run is not None
            ]
        else:
            QMessageBox.information(
                self,
                "Nothing selected",
                "Select scored rows to re-judge, or use "
                "'Judge everything unjudged' for new runs.",
            )
            return
        self._queue(runs)

    def _judge_unjudged(self) -> None:
        runs = self.context.store.unjudged_runs()
        if not runs:
            self.context.status.emit("Every run has already been judged.")
            return
        self._queue(runs)


def _scorecard_markdown(card: Scorecard, scenario) -> str:
    lines = [
        f"# Scorecard — {card.variant_id}",
        "",
        f"Judge: `{card.judge_model}` · mode: {card.mode}",
        "",
        f"- Composite: **{card.composite:.2f}**",
        f"- Recall: {card.recall:.2f}"
        if card.mode == GROUNDED_MODE
        else "- Recall: n/a (free-form)",
        f"- Precision: {card.precision:.2f}",
        f"- Rubric average: {card.rubric.mean:.1f} out of 5",
        "",
        "## Rubric",
        "",
    ]
    for name in (
        "faithfulness",
        "coverage",
        "structure",
        "attribution",
        "concision",
        "actionability",
    ):
        lines.append(f"- {name}: {getattr(card.rubric, name):.0f}")

    structure = card.structure
    lines.extend(
        [
            "",
            "## Structure checks",
            "",
            f"- Score: {structure.score:.2f}",
            f"- Words: {structure.word_count:,} across {structure.heading_count} headings",
        ]
    )
    if structure.missing_headings:
        lines.append(f"- Missing sections: {', '.join(structure.missing_headings)}")
    if structure.leaked_headings:
        lines.append(
            f"- Sections that should have been omitted: {', '.join(structure.leaked_headings)}"
        )
    if structure.action_table_required:
        lines.append(
            f"- Action table: {'present' if structure.has_action_table else 'MISSING'}"
        )

    if card.fact_verdicts:
        covered = sum(1 for item in card.fact_verdicts if item.status == STATUS_COVERED)
        lines.extend(
            [
                "",
                f"## Facts ({covered} of {len(card.fact_verdicts)} fully covered)",
                "",
            ]
        )
        facts = {fact.fact_id: fact for fact in (scenario.facts if scenario else ())}
        for verdict in card.fact_verdicts:
            fact = facts.get(verdict.fact_id)
            text = fact.text if fact else verdict.fact_id
            mark = STATUS_MARK.get(verdict.status, verdict.status)
            lines.append(f"- **{mark}** — {text}")
            if verdict.evidence:
                lines.append(f"    - {verdict.evidence}")

    if card.unsupported_claims:
        lines.extend(["", "## Claims the meeting does not support", ""])
        lines.extend(f"- {claim}" for claim in card.unsupported_claims)
    if card.asserted_distractors:
        lines.extend(["", "## Abandoned ideas reported as real", ""])
        lines.extend(f"- {claim}" for claim in card.asserted_distractors)
    if card.notes:
        lines.extend(["", "## Judge's note", "", card.notes])
    if card.error:
        lines.extend(["", "## Error", "", card.error])
    return "\n".join(lines)


def _judge_job(context: LabContext, run, transcript, scenario, settings: JudgeSettings):
    def execute(job_context: JobContext) -> Scorecard:
        card = judge_run(
            run,
            transcript,
            scenario,
            JudgeSettings(
                model_name=job_context.model_name,
                num_ctx=job_context.num_ctx,
                temperature=settings.temperature,
            ),
            on_progress=job_context.progress,
            cancel_event=job_context.cancel_event,
        )
        context.store.scores.save(card)
        return card

    return execute
