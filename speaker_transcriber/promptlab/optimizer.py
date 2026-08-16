"""Turn measured failures and human verdicts into a new candidate prompt.

The optimizer never writes a shipped file. It produces a candidate that lands in
the variant store, where it has to earn promotion the same way any hand-written
variant does: by winning A/B comparisons against the prompt it is trying to
replace.

The quality of the rewrite is almost entirely a function of the evidence bundle,
so this module spends most of its effort assembling specific, quoted failures
rather than aggregate scores. "Recall is 0.62" tells a model nothing it can act
on; "these eleven facts were dropped, nine of them action items with owners"
does.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from speaker_transcriber.promptlab.ab import decided_pairs, standings, tag_tally
from speaker_transcriber.promptlab.judge import parse_judge_json
from speaker_transcriber.promptlab.lab_prompts import get_lab_prompt
from speaker_transcriber.promptlab.ollama_client import LabOllama
from speaker_transcriber.promptlab.promptset import (
    create_variant,
    stage_diff,
    stage_text,
)
from speaker_transcriber.promptlab.store import LabStore
from speaker_transcriber.promptlab.types import (
    AUTHOR_OPTIMIZER,
    GROUNDED_MODE,
    OptimizerCandidate,
    PROMPT_STAGES,
    PromptVariant,
    STATUS_COVERED,
    Scenario,
    fingerprint,
    new_id,
)


LOGGER = logging.getLogger("speaker_transcriber.promptlab.optimizer")

MAX_MISSED_FACTS = 14
MAX_CLAIMS = 10
MAX_NOTES = 10

STAGE_GUIDANCE = {
    "system": (
        "This is the standing instruction sent with every call in the pipeline. "
        "Only change it for problems that appear at every stage: voice, "
        "faithfulness, and the output contract."
    ),
    "chunk": (
        "This runs once per slice of transcript. Dropped facts, lost owners, and "
        "missing numbers or dates almost always originate here, because content "
        "that never leaves this stage cannot be recovered later."
    ),
    "merge": (
        "This builds the overview from the slice notes. Missing or misordered "
        "sections, and an overview that reads like a list of fragments, "
        "originate here."
    ),
    "validate": (
        "This checks the overview against the slice notes and repairs it. Facts "
        "that survived the chunk stage but never reached the finished document "
        "should have been caught here."
    ),
    "format": (
        "This is a presentation pass over a finished document. It must not add, "
        "remove, or reinterpret content; only change it for layout and "
        "formatting failures."
    ),
}


@dataclass(frozen=True)
class EvidenceBundle:
    style_id: str
    stage: str
    variant_id: str
    runs_examined: int = 0
    mean_composite: float = 0.0
    mean_recall: float = 0.0
    mean_precision: float = 0.0
    mean_rubric: float = 0.0
    weakest_dimensions: tuple[str, ...] = ()
    missed_facts: tuple[str, ...] = ()
    unsupported_claims: tuple[str, ...] = ()
    structure_failures: tuple[str, ...] = ()
    human_notes: tuple[str, ...] = ()
    complaint_tags: tuple[str, ...] = ()
    head_to_head: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return not (
            self.missed_facts
            or self.unsupported_claims
            or self.structure_failures
            or self.human_notes
        )

    def to_markdown(self) -> str:
        blocks = [
            f"# Measured performance of this prompt\n\n"
            f"- Runs examined: {self.runs_examined}\n"
            f"- Composite score: {self.mean_composite:.2f} out of 1.00\n"
            f"- Fact recall: {self.mean_recall:.2f}\n"
            f"- Precision (share of claims that were supported): {self.mean_precision:.2f}\n"
            f"- Judge rubric average: {self.mean_rubric:.2f} out of 5"
        ]
        if self.weakest_dimensions:
            blocks.append(
                "# Weakest rubric dimensions\n\n"
                + "\n".join(f"- {line}" for line in self.weakest_dimensions)
            )
        if self.missed_facts:
            blocks.append(
                "# Facts the notes failed to carry\n\n"
                + "\n".join(f"- {line}" for line in self.missed_facts)
            )
        if self.unsupported_claims:
            blocks.append(
                "# Claims the notes made that the meeting does not support\n\n"
                + "\n".join(f"- {line}" for line in self.unsupported_claims)
            )
        if self.structure_failures:
            blocks.append(
                "# Structural failures\n\n"
                + "\n".join(f"- {line}" for line in self.structure_failures)
            )
        if self.complaint_tags:
            blocks.append(
                "# What a human complained about when this prompt lost\n\n"
                + "\n".join(f"- {line}" for line in self.complaint_tags)
            )
        if self.human_notes:
            blocks.append(
                "# Human comments from side-by-side comparisons\n\n"
                + "\n".join(f"- {line}" for line in self.human_notes)
            )
        if self.head_to_head:
            blocks.append(f"# Head to head\n\n{self.head_to_head}")
        if self.warnings:
            blocks.append(
                "# Caveats\n\n" + "\n".join(f"- {line}" for line in self.warnings)
            )
        return "\n\n".join(blocks)

    def digest(self) -> str:
        return fingerprint({"evidence": self.to_markdown()})


TAG_MEANINGS = {
    "missed_facts": "left out material that mattered",
    "hallucinated": "stated things the meeting did not support",
    "wrong_owner": "attributed work or decisions to the wrong person",
    "too_long": "padded, longer than the substance justified",
    "too_terse": "compressed past the point of usefulness",
    "bad_structure": "poorly organized or sections in the wrong order",
    "weak_actions": "action items were vague or unassigned",
    "tone_off": "wrong register for the document",
}


def _weakest_dimensions(cards: list[Any]) -> tuple[str, ...]:
    if not cards:
        return ()
    from speaker_transcriber.promptlab.types import RUBRIC_DIMENSIONS

    averages = []
    for name in RUBRIC_DIMENSIONS:
        values = [getattr(card.rubric, name) for card in cards]
        averages.append((sum(values) / len(values), name))
    averages.sort()
    return tuple(f"{name}: {score:.1f} out of 5" for score, name in averages[:3])


def build_evidence(
    store: LabStore,
    variant: PromptVariant,
    stage: str,
    *,
    style_id: str = "",
) -> EvidenceBundle:
    """Gather everything known about how this variant's notes actually failed."""
    if stage not in PROMPT_STAGES:
        raise KeyError(f"Unknown prompt stage '{stage}'")
    style = style_id or variant.style_id

    runs = [
        run
        for run in store.runs.all()
        if run.variant_id == variant.variant_id and run.style_id == style
    ]
    run_ids = {run.run_id for run in runs}
    cards = [
        card
        for card in store.scores.all()
        if card.run_id in run_ids and not card.error
    ]

    scenarios: dict[str, Scenario] = {}
    for run in runs:
        if run.scenario_id and run.scenario_id not in scenarios:
            scenario = store.scenarios.get(run.scenario_id)
            if scenario is not None:
                scenarios[run.scenario_id] = scenario
    runs_by_id = {run.run_id: run for run in runs}

    missed: Counter[str] = Counter()
    for card in cards:
        run = runs_by_id.get(card.run_id)
        scenario = scenarios.get(run.scenario_id) if run else None
        if scenario is None:
            continue
        for verdict in card.fact_verdicts:
            if verdict.status == STATUS_COVERED:
                continue
            fact = scenario.fact_by_id(verdict.fact_id)
            if fact is None:
                continue
            missed[f"({fact.kind}, {verdict.status}) {fact.text}"] += 1

    missed_lines = tuple(
        f"{text}" + (f"  [dropped in {count} runs]" if count > 1 else "")
        for text, count in missed.most_common(MAX_MISSED_FACTS)
    )

    claims: list[str] = []
    for card in cards:
        claims.extend(card.unsupported_claims)
        claims.extend(
            f"reported an abandoned idea as real: {item}"
            for item in card.asserted_distractors
        )
    claim_lines = tuple(dict.fromkeys(claims))[:MAX_CLAIMS]

    structure: Counter[str] = Counter()
    for card in cards:
        for heading in card.structure.missing_headings:
            structure[f"section `## {heading}` was missing"] += 1
        for heading in card.structure.leaked_headings:
            structure[f"section `## {heading}` appeared even though it was turned off"] += 1
        if card.structure.action_table_required and not card.structure.has_action_table:
            structure["the action table was missing or not a table"] += 1
    structure_lines = tuple(
        f"{text} ({count} of {len(cards)} runs)" for text, count in structure.most_common(8)
    )

    notes: list[str] = []
    for item in decided_pairs(store, style_id=style):
        if item.is_tie or item.loser_variant_id != variant.variant_id:
            continue
        if item.verdict.notes:
            notes.append(item.verdict.notes)
    note_lines = tuple(dict.fromkeys(notes))[-MAX_NOTES:]

    tags = tag_tally(store, variant.variant_id, style_id=style)
    tag_lines = tuple(
        f"{TAG_MEANINGS.get(tag, tag)} ({count} times)"
        for tag, count in sorted(tags.items(), key=lambda item: -item[1])
    )

    table = standings(store, style_id=style)
    row = next((entry for entry in table if entry.variant_id == variant.variant_id), None)
    head_to_head = ""
    if row is not None and (row.wins or row.losses or row.ties):
        head_to_head = (
            f"{row.wins} wins, {row.losses} losses, {row.ties} ties across "
            f"side-by-side comparisons (Elo {row.elo:.0f})."
        )

    warnings: list[str] = []
    if len(cards) < 3:
        warnings.append(
            f"Only {len(cards)} judged run(s) informed this evidence, so the "
            "signal is weak; prefer a small, targeted edit."
        )
    if not note_lines and not tag_lines:
        warnings.append("No human comparisons have been recorded for this prompt yet.")

    def mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    return EvidenceBundle(
        style_id=style,
        stage=stage,
        variant_id=variant.variant_id,
        runs_examined=len(cards),
        mean_composite=mean([card.composite for card in cards]),
        mean_recall=mean([card.recall for card in cards if card.mode == GROUNDED_MODE]),
        mean_precision=mean([card.precision for card in cards]),
        mean_rubric=mean([card.rubric.mean for card in cards]),
        weakest_dimensions=_weakest_dimensions(cards),
        missed_facts=missed_lines,
        unsupported_claims=claim_lines,
        structure_failures=structure_lines,
        human_notes=note_lines,
        complaint_tags=tag_lines,
        head_to_head=head_to_head,
        warnings=tuple(warnings),
    )


@dataclass(frozen=True)
class OptimizerSettings:
    model_name: str
    num_ctx: int = 16384
    temperature: float = 0.3


def _optimizer_prompt(current: str, stage: str, evidence: EvidenceBundle) -> str:
    return (
        f"# The prompt to improve\n\n"
        f"This is the `{stage}` prompt of the summarizer's pipeline. "
        f"{STAGE_GUIDANCE.get(stage, '')}\n\n"
        "```\n"
        f"{current.strip()}\n"
        "```\n\n"
        f"{evidence.to_markdown()}\n\n"
        "# Your task\n\n"
        f"Return the improved `{stage}` prompt as JSON, in the shape you were "
        "given. Address the failures above and change nothing else."
    )


def propose_prompt(
    store: LabStore,
    variant: PromptVariant,
    stage: str,
    settings: OptimizerSettings,
    *,
    evidence: EvidenceBundle | None = None,
    on_progress: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
    client: Any = None,
) -> OptimizerCandidate:
    """Ask the optimizer model for a better version of one prompt stage."""
    if stage not in PROMPT_STAGES:
        raise KeyError(f"Unknown prompt stage '{stage}'")

    def emit(fraction: float, message: str) -> None:
        if on_progress is not None:
            on_progress(min(max(fraction, 0.0), 1.0), message)

    emit(0.05, "Gathering evidence…")
    bundle = evidence or build_evidence(store, variant, stage)
    current = stage_text(variant, stage)

    emit(0.2, f"Rewriting the {stage} prompt with {settings.model_name}…")
    model = LabOllama(
        settings.model_name,
        num_ctx=settings.num_ctx,
        temperature=settings.temperature,
        cancel_event=cancel_event,
        client=client,
    )
    raw = model.generate(
        _optimizer_prompt(current, stage, bundle),
        system=get_lab_prompt("optimizer"),
        num_predict=4096,
    )

    try:
        payload = parse_judge_json(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"The optimizer did not return usable JSON: {exc}"
        ) from exc

    proposed = str(payload.get("prompt") or "").strip()
    if not proposed:
        raise RuntimeError("The optimizer returned an empty prompt.")
    if proposed == current.strip():
        raise RuntimeError("The optimizer returned the prompt unchanged.")

    emit(1.0, "Candidate ready")
    return OptimizerCandidate(
        candidate_id=new_id("cand"),
        style_id=variant.style_id,
        stage=stage,
        base_variant_id=variant.variant_id,
        prompt_text=proposed,
        changelog=str(payload.get("changelog") or "").strip(),
        evidence_digest=bundle.digest(),
        model_name=settings.model_name,
    )


def candidate_diff(store: LabStore, candidate: OptimizerCandidate, base: PromptVariant) -> str:
    return stage_diff(
        stage_text(base, candidate.stage),
        candidate.prompt_text,
        label=f"{candidate.style_id}/{candidate.stage}",
    )


def save_candidate(
    store: LabStore,
    candidate: OptimizerCandidate,
    base: PromptVariant,
    *,
    label: str = "",
) -> tuple[PromptVariant, OptimizerCandidate]:
    """File a candidate as a variant so it can be run and compared."""
    stages = dict(base.stages)
    stages[candidate.stage] = candidate.prompt_text
    variant = create_variant(
        store,
        candidate.style_id,
        stages,
        label=label or f"Optimizer {candidate.stage} on {base.label}",
        author=AUTHOR_OPTIMIZER,
        parent_id=base.variant_id,
        rationale=candidate.changelog,
    )
    recorded = OptimizerCandidate(
        candidate_id=candidate.candidate_id,
        style_id=candidate.style_id,
        stage=candidate.stage,
        base_variant_id=candidate.base_variant_id,
        prompt_text=candidate.prompt_text,
        changelog=candidate.changelog,
        evidence_digest=candidate.evidence_digest,
        model_name=candidate.model_name,
        saved_variant_id=variant.variant_id,
        created_at=candidate.created_at,
    )
    store.candidates.save(recorded)
    return variant, recorded


def stage_failure_hint(store: LabStore, variant: PromptVariant, style_id: str = "") -> dict[str, str]:
    """Which stage each observed failure most likely belongs to.

    A rough router, so the Optimize tab can suggest a stage instead of making
    the user guess which of five prompts caused a dropped action item.
    """
    style = style_id or variant.style_id
    evidence = build_evidence(store, variant, "chunk", style_id=style)
    hints: dict[str, str] = defaultdict(str)
    if evidence.missed_facts:
        hints["chunk"] = f"{len(evidence.missed_facts)} distinct facts were dropped."
    if evidence.structure_failures:
        hints["merge"] = f"{len(evidence.structure_failures)} structural failures."
    if evidence.unsupported_claims:
        hints["validate"] = (
            f"{len(evidence.unsupported_claims)} unsupported claims reached the document."
        )
    return dict(hints)
