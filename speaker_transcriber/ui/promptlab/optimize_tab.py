"""Leaderboard, evidence, and the optimizer that rewrites a prompt stage."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from speaker_transcriber.promptlab.ab import judge_agreement, standings
from speaker_transcriber.promptlab.optimizer import (
    EvidenceBundle,
    OptimizerSettings,
    build_evidence,
    candidate_diff,
    propose_prompt,
    save_candidate,
    stage_failure_hint,
)
from speaker_transcriber.promptlab.promptset import (
    list_variants,
    load_variant,
    promote_variant,
    restore_variant,
    variant_diff,
)
from speaker_transcriber.promptlab.types import (
    PROMPT_STAGES,
    OptimizerCandidate,
    PromptVariant,
    new_id,
)
from speaker_transcriber.ui.promptlab.common import (
    LabContext,
    MarkdownView,
    ctx_combo,
    fill_models,
    heading,
    hint,
    make_table,
    model_combo,
    monospace,
    set_row,
    style_combo,
)
from speaker_transcriber.ui.promptlab.workers import KIND_OPTIMIZE, JobContext, LabJob


class OptimizeTab(QWidget):
    def __init__(self, context: LabContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._candidate: OptimizerCandidate | None = None
        self._build()
        self.context.models_changed.connect(self._on_models)
        self.context.scores_changed.connect(self.refresh)
        self.context.verdicts_changed.connect(self.refresh)
        self.context.variants_changed.connect(self._refresh_variants)
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._leaderboard())

        lower = QWidget()
        row = QHBoxLayout(lower)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._controls(), 0)

        self.views = QTabWidget()
        self.evidence_view = MarkdownView()
        self.diff_view = monospace(MarkdownView())
        self.candidate_view = monospace(MarkdownView())
        self.views.addTab(self.evidence_view, "Evidence")
        self.views.addTab(self.diff_view, "Diff")
        self.views.addTab(self.candidate_view, "Candidate prompt")
        row.addWidget(self.views, 1)
        splitter.addWidget(lower)
        splitter.setSizes([260, 520])
        layout.addWidget(splitter)

    def _leaderboard(self) -> QWidget:
        panel = QWidget()
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        header.addWidget(heading("Leaderboard"))
        self.style_selector = style_combo(self.context.settings.style_id)
        self.style_selector.currentIndexChanged.connect(self._on_style)
        header.addWidget(self.style_selector)
        self.agreement_label = QLabel("")
        self.agreement_label.setWordWrap(True)
        header.addWidget(self.agreement_label, 1)
        column.addLayout(header)

        self.table = make_table(
            [
                "Variant",
                "Elo",
                "Win rate",
                "W-L-T",
                "Runs",
                "Composite",
                "Recall",
                "Precision",
                "Rubric",
            ]
        )
        column.addWidget(self.table)
        return panel

    def _controls(self) -> QWidget:
        settings = self.context.settings
        panel = QWidget()
        panel.setMaximumWidth(340)
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 8, 0)

        box = QGroupBox("Rewrite a prompt")
        form = QFormLayout(box)
        self.variant_combo = QComboBox()
        self.variant_combo.currentIndexChanged.connect(self._on_variant)
        form.addRow("Base variant", self.variant_combo)
        self.stage_combo = QComboBox()
        for stage in PROMPT_STAGES:
            self.stage_combo.addItem(stage, stage)
        self.stage_combo.setCurrentIndex(1)
        form.addRow("Stage", self.stage_combo)
        self.model = model_combo(settings.optimizer_model)
        form.addRow("Model", self.model)
        self.num_ctx = ctx_combo(settings.optimizer_num_ctx)
        form.addRow("Context", self.num_ctx)
        column.addWidget(box)

        self.stage_hint = hint("")
        column.addWidget(self.stage_hint)

        self.gather_button = QPushButton("Gather evidence")
        self.gather_button.clicked.connect(self._gather)
        column.addWidget(self.gather_button)

        self.propose_button = QPushButton("Generate candidate")
        self.propose_button.clicked.connect(self._propose)
        column.addWidget(self.propose_button)

        self.save_button = QPushButton("Save candidate as variant")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save_candidate)
        column.addWidget(self.save_button)

        column.addWidget(heading("Shipped prompts"))
        column.addWidget(
            hint(
                "Promoting overwrites the prompt files the application ships. "
                "The text being replaced is snapshotted as a backup variant "
                "first, so it can be restored from here."
            )
        )
        self.promote_button = QPushButton("Promote selected variant to shipped")
        self.promote_button.clicked.connect(self._promote)
        column.addWidget(self.promote_button)
        self.restore_button = QPushButton("Restore selected backup")
        self.restore_button.clicked.connect(self._restore)
        column.addWidget(self.restore_button)

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
        fill_models(self.model, names, self.context.settings.optimizer_model)

    def _on_variant(self) -> None:
        variant = self._selected_variant()
        if variant is None:
            return
        hints = stage_failure_hint(self.context.store, variant, self.style_id)
        if hints:
            self.stage_hint.setText(
                "Where the evidence points: "
                + "; ".join(f"{stage} — {text}" for stage, text in hints.items())
            )
        else:
            self.stage_hint.setText(
                "No judged runs for this variant yet, so there is nothing for the "
                "optimizer to work from."
            )

    def refresh(self) -> None:
        self._refresh_variants()
        labels = {
            variant.variant_id: variant.label
            for variant in list_variants(self.context.store, self.style_id)
        }
        rows = standings(self.context.store, style_id=self.style_id, labels=labels)
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            set_row(
                self.table,
                index,
                [
                    row.label,
                    f"{row.elo:.0f}",
                    f"{row.win_rate * 100:.0f}%" if row.decided or row.ties else "—",
                    f"{row.wins}-{row.losses}-{row.ties}",
                    str(row.runs),
                    f"{row.mean_composite:.2f}",
                    f"{row.mean_recall:.2f}",
                    f"{row.mean_precision:.2f}",
                    f"{row.mean_rubric:.1f}",
                ],
                identifier=row.variant_id,
            )
        agreement = judge_agreement(self.context.store, style_id=self.style_id)
        self.agreement_label.setText(f"Judge agreement: {agreement.summary}")

    def _refresh_variants(self) -> None:
        chosen = self.variant_combo.currentData()
        self.variant_combo.blockSignals(True)
        self.variant_combo.clear()
        for variant in list_variants(self.context.store, self.style_id):
            self.variant_combo.addItem(variant.label, variant.variant_id)
        index = self.variant_combo.findData(chosen)
        if index >= 0:
            self.variant_combo.setCurrentIndex(index)
        self.variant_combo.blockSignals(False)
        self._on_variant()

    def _selected_variant(self) -> PromptVariant | None:
        variant_id = str(self.variant_combo.currentData() or "")
        if not variant_id:
            return None
        try:
            return load_variant(self.context.store, self.style_id, variant_id)
        except KeyError:
            return None

    # Actions

    def _gather(self) -> EvidenceBundle | None:
        variant = self._selected_variant()
        if variant is None:
            return None
        stage = str(self.stage_combo.currentData())
        bundle = build_evidence(self.context.store, variant, stage, style_id=self.style_id)
        self.evidence_view.show_markdown(bundle.to_markdown())
        self.views.setCurrentIndex(0)
        return bundle

    def _propose(self) -> None:
        variant = self._selected_variant()
        if variant is None:
            return
        bundle = self._gather()
        if bundle is None:
            return
        if bundle.is_empty:
            answer = QMessageBox.question(
                self,
                "No failures recorded",
                "Nothing has been measured against this prompt yet, so the "
                "optimizer would be guessing. Generate a candidate anyway?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        settings = self.context.settings
        settings.optimizer_model = self.model.currentText().strip()
        settings.optimizer_num_ctx = int(self.num_ctx.currentData())
        self.context.save_settings()
        if not settings.optimizer_model:
            QMessageBox.warning(
                self, "No optimizer model", "Choose an Ollama model to rewrite the prompt."
            )
            return

        stage = str(self.stage_combo.currentData())
        optimizer = OptimizerSettings(
            model_name=settings.optimizer_model, num_ctx=settings.optimizer_num_ctx
        )
        self.context.runner.enqueue(
            LabJob(
                job_id=new_id("job"),
                kind=KIND_OPTIMIZE,
                label=f"Rewrite {self.style_id}/{stage} from {variant.label}",
                model_name=optimizer.model_name,
                num_ctx=optimizer.num_ctx,
                run=_optimize_job(self.context, variant, stage, optimizer, bundle),
                payload={"variant_id": variant.variant_id, "stage": stage},
            )
        )
        self.context.status.emit(f"Queued a rewrite of the {stage} prompt.")

    def show_candidate(self, candidate: OptimizerCandidate) -> None:
        """Called by the window when an optimize job finishes."""
        base = self._selected_variant()
        self._candidate = candidate
        self.candidate_view.show_plain(candidate.prompt_text)
        if base is not None:
            diff = candidate_diff(self.context.store, candidate, base)
            self.diff_view.show_plain(diff or "The candidate is identical to the base.")
        changelog = candidate.changelog or "(the optimizer gave no changelog)"
        self.evidence_view.show_markdown(
            self.evidence_view.toMarkdown() + f"\n\n# Optimizer changelog\n\n{changelog}"
        )
        self.save_button.setEnabled(True)
        self.views.setCurrentIndex(1)

    def _save_candidate(self) -> None:
        if self._candidate is None:
            return
        base = self._selected_variant()
        if base is None:
            return
        variant, _ = save_candidate(self.context.store, self._candidate, base)
        self._candidate = None
        self.save_button.setEnabled(False)
        self.context.variants_changed.emit()
        self.context.status.emit(
            f"Saved «{variant.label}». Run it against the same transcripts to "
            "find out whether it is actually better."
        )

    def _promote(self) -> None:
        variant = self._selected_variant()
        if variant is None or variant.is_shipped:
            QMessageBox.information(
                self,
                "Nothing to promote",
                "Choose a saved variant. The shipped variant is already live.",
            )
            return
        stages = ", ".join(variant.overridden_stages)
        answer = QMessageBox.question(
            self,
            "Promote to shipped",
            f"Overwrite the shipped {stages} prompt(s) for "
            f"{self.style_id} with «{variant.label}»?\n\n"
            "The current text is saved as a backup variant first.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        backup = promote_variant(self.context.store, variant)
        self.context.variants_changed.emit()
        self.context.status.emit(
            f"Promoted «{variant.label}». Previous text saved as {backup.variant_id}."
        )

    def _restore(self) -> None:
        variant = self._selected_variant()
        if variant is None or not variant.variant_id.startswith("bak-"):
            QMessageBox.information(
                self,
                "Not a backup",
                "Choose a backup variant (their ids begin with 'bak-').",
            )
            return
        restore_variant(self.context.store, variant)
        self.context.variants_changed.emit()
        self.context.status.emit(f"Restored the shipped prompts from {variant.variant_id}.")

    def show_variant_diff(self, variant: PromptVariant, stage: str) -> None:
        self.diff_view.show_plain(
            variant_diff(variant, stage) or "Identical to the shipped prompt."
        )
        self.views.setCurrentIndex(1)


def _optimize_job(
    context: LabContext,
    variant: PromptVariant,
    stage: str,
    settings: OptimizerSettings,
    evidence: EvidenceBundle,
):
    def run(job_context: JobContext) -> OptimizerCandidate:
        return propose_prompt(
            context.store,
            variant,
            stage,
            OptimizerSettings(
                model_name=job_context.model_name,
                num_ctx=job_context.num_ctx,
                temperature=settings.temperature,
            ),
            evidence=evidence,
            on_progress=job_context.progress,
            cancel_event=job_context.cancel_event,
        )

    return run
