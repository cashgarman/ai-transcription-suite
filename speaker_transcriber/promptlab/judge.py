"""Score a summary: deterministic checks first, then a local judge model.

The model is the weaker of the two signals. It reads well and catches meaning,
but it drifts between runs and can be talked into approving anything. So every
check that can be made without a model is made without one — headings, tables,
length, excluded-section leakage — and the model is asked only for the
judgements that genuinely need reading comprehension.

Both rubrics return one JSON object. Models being what they are, the parser
tolerates code fences and surrounding chatter, and one repair call is made
before a run is recorded as unjudgeable.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from speaker_transcriber.prompts import (
    SEGMENT_NOTES_SECTION_ID,
    excluded_section_headings,
    get_style,
    normalize_excluded_sections,
    style_sections,
)
from speaker_transcriber.promptlab.lab_prompts import get_lab_prompt
from speaker_transcriber.promptlab.ollama_client import LabOllama
from speaker_transcriber.promptlab.types import (
    FREEFORM_MODE,
    FactVerdict,
    GROUNDED_MODE,
    GeneratedTranscript,
    RUBRIC_DIMENSIONS,
    RubricScores,
    STATUS_MISSING,
    Scenario,
    Scorecard,
    StructureMetrics,
    SummaryRun,
)


LOGGER = logging.getLogger("speaker_transcriber.promptlab.judge")

CHARS_PER_TOKEN = 4
TRANSCRIPT_BUDGET_FRACTION = 0.55
"""Share of the judge's context the transcript may occupy in free-form mode."""

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(?P<text>.+?)\s*#*\s*$", re.MULTILINE)
_TABLE_ROW = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+\S", re.MULTILINE)
_SENTENCE = re.compile(r"[.!?](?:\s|$)")
_ACTION_HEADER = re.compile(r"\|[^|\n]*owner[^|\n]*\|[^|\n]*action[^|\n]*\|", re.IGNORECASE)


@dataclass(frozen=True)
class JudgeSettings:
    model_name: str
    num_ctx: int = 8192
    temperature: float = 0.0
    """Zero by default: a judge that disagrees with itself cannot rank prompts."""


def document_headings(markdown: str) -> tuple[str, ...]:
    return tuple(match.group("text").strip() for match in _HEADING.finditer(markdown or ""))


def has_action_table(markdown: str) -> bool:
    if _ACTION_HEADER.search(markdown or ""):
        return True
    # A table under an action heading counts even when its columns are renamed.
    lowered = (markdown or "").lower()
    for marker in ("## action items", "## follow-ups", "## who owns what", "## blockers"):
        index = lowered.find(marker)
        if index == -1:
            continue
        window = markdown[index : index + 1200]
        if len(_TABLE_ROW.findall(window)) >= 2:
            return True
    return False


def claim_count(markdown: str) -> int:
    """A rough count of assertions, used to put unsupported claims in proportion."""
    body = markdown or ""
    bullets = len(_BULLET.findall(body))
    rows = max(0, len(_TABLE_ROW.findall(body)) - 2)
    prose = body
    for pattern in (_HEADING, _TABLE_ROW, _BULLET):
        prose = pattern.sub("", prose)
    sentences = len(_SENTENCE.findall(prose))
    return max(1, bullets + rows + sentences)


def structure_metrics(
    markdown: str,
    style_id: str,
    excluded_sections: tuple[str, ...] = (),
) -> StructureMetrics:
    """Heading, table, and size checks that need no model at all."""
    style = get_style(style_id)
    excluded = set(normalize_excluded_sections(style_id, excluded_sections))
    present = {heading.lower() for heading in document_headings(markdown)}

    expected: list[str] = []
    missing: list[str] = []
    for section in style_sections(style_id):
        if section.section_id in excluded or section.section_id == SEGMENT_NOTES_SECTION_ID:
            continue
        if not section.headings:
            continue
        expected.append(section.headings[0])
        if not any(heading.lower() in present for heading in section.headings):
            missing.append(section.headings[0])

    leaked = [
        heading
        for heading in excluded_section_headings(style_id, tuple(excluded))
        if heading.lower() in present
    ]

    required_table = style.requires_action_table(tuple(excluded)) and any(
        section.section_id in ("action_items", "follow_ups", "owners", "blockers")
        for section in style_sections(style_id)
        if section.section_id not in excluded
    )

    return StructureMetrics(
        expected_headings=tuple(expected),
        missing_headings=tuple(missing),
        leaked_headings=tuple(leaked),
        has_action_table=has_action_table(markdown),
        action_table_required=required_table,
        heading_count=len(document_headings(markdown)),
        word_count=len((markdown or "").split()),
    )


def parse_judge_json(text: str) -> dict[str, Any]:
    """The first JSON object in `text`, however the model wrapped it."""
    body = str(text or "").strip()
    if not body:
        raise ValueError("The judge returned nothing.")
    fenced = re.search(r"```(?:json)?\s*(.+?)```", body, re.DOTALL)
    if fenced:
        body = fenced.group(1).strip()
    start = body.find("{")
    if start == -1:
        raise ValueError("The judge returned no JSON object.")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(body)):
        char = body[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = body[start : index + 1]
                return json.loads(candidate)
    raise ValueError("The judge's JSON object was never closed.")


def _rubric_from(payload: Any) -> RubricScores:
    scores = payload.get("scores") if isinstance(payload, dict) else None
    if not isinstance(scores, dict):
        scores = payload if isinstance(payload, dict) else {}
    values: dict[str, float] = {}
    for name in RUBRIC_DIMENSIONS:
        raw = scores.get(name)
        try:
            number = float(raw)
        except (TypeError, ValueError):
            number = 0.0
        values[name] = max(0.0, min(5.0, number))
    return RubricScores(**values)


def _string_list(payload: Any, key: str) -> tuple[str, ...]:
    items = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return ()
    cleaned = []
    for item in items:
        if isinstance(item, dict):
            item = item.get("claim") or item.get("text") or json.dumps(item, ensure_ascii=False)
        text = str(item).strip()
        if text:
            cleaned.append(text)
    return tuple(cleaned)


def _fact_verdicts(payload: Any, scenario: Scenario | None) -> tuple[FactVerdict, ...]:
    if scenario is None:
        return ()
    reported: dict[str, FactVerdict] = {}
    items = payload.get("facts") if isinstance(payload, dict) else None
    for item in items if isinstance(items, list) else ():
        if not isinstance(item, dict):
            continue
        verdict = FactVerdict.from_dict(item)
        if verdict.fact_id:
            reported[verdict.fact_id] = verdict
    # A fact the judge simply did not mention counts as missing, never as covered.
    return tuple(
        reported.get(fact.fact_id, FactVerdict(fact.fact_id, STATUS_MISSING, "Not addressed by the judge."))
        for fact in scenario.facts
    )


def recall_for(scenario: Scenario, verdicts: tuple[FactVerdict, ...]) -> float:
    if not scenario.facts:
        return 0.0
    by_id = {verdict.fact_id: verdict for verdict in verdicts}
    earned = 0.0
    for fact in scenario.facts:
        verdict = by_id.get(fact.fact_id)
        if verdict is not None:
            earned += verdict.credit * fact.weight
    total = scenario.total_weight
    return round(earned / total, 4) if total else 0.0


def precision_for(
    markdown: str,
    unsupported: tuple[str, ...],
    asserted_distractors: tuple[str, ...],
) -> float:
    """One minus the share of assertions that are wrong.

    A distractor reported as settled fact counts double: inventing a decision
    the room explicitly rejected is worse than an ordinary overreach.
    """
    penalty = len(unsupported) + 2 * len(asserted_distractors)
    if penalty <= 0:
        return 1.0
    return round(max(0.0, 1.0 - penalty / claim_count(markdown)), 4)


def composite_for(
    mode: str,
    recall: float,
    precision: float,
    rubric: RubricScores,
    structure: StructureMetrics,
) -> float:
    if mode == GROUNDED_MODE:
        score = (
            0.40 * recall
            + 0.25 * precision
            + 0.20 * rubric.normalized
            + 0.15 * structure.score
        )
    else:
        score = 0.55 * rubric.normalized + 0.25 * precision + 0.20 * structure.score
    return round(max(0.0, min(1.0, score)), 4)


def _facts_block(scenario: Scenario) -> str:
    lines = []
    for fact in scenario.facts:
        owner = f" (owner: {fact.owner})" if fact.owner else ""
        lines.append(f"- {fact.fact_id} [{fact.kind}, {fact.salience}]{owner}: {fact.text}")
    return "\n".join(lines) or "- (none)"


def _distractors_block(scenario: Scenario) -> str:
    lines = [f"- {item.text}" for item in scenario.distractors]
    return "\n".join(lines) or "- (none)"


def _truncate_middle(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    head = int(limit * 0.6)
    tail = limit - head
    return (
        text[:head]
        + "\n\n[... middle of the transcript omitted to fit the judge's context ...]\n\n"
        + text[-tail:]
    )


def _grounded_prompt(scenario: Scenario, markdown: str) -> str:
    return (
        "# Facts the meeting really contained\n\n"
        f"{_facts_block(scenario)}\n\n"
        "# Ideas raised and then abandoned\n\n"
        f"{_distractors_block(scenario)}\n\n"
        "# The notes to grade\n\n"
        f"{markdown.strip()}"
    )


def _reference_free_prompt(transcript_text: str, markdown: str, budget: int) -> str:
    return (
        "# Transcript\n\n"
        f"{_truncate_middle(transcript_text.strip(), budget)}\n\n"
        "# The notes to grade\n\n"
        f"{markdown.strip()}"
    )


def judge_run(
    run: SummaryRun,
    transcript: GeneratedTranscript,
    scenario: Scenario | None,
    settings: JudgeSettings,
    *,
    on_progress: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
    client: Any = None,
) -> Scorecard:
    """Grade one run. Grounded scenarios get fact-by-fact recall; others do not."""

    def emit(fraction: float, message: str) -> None:
        if on_progress is not None:
            on_progress(min(max(fraction, 0.0), 1.0), message)

    grounded = scenario is not None and scenario.is_grounded and bool(scenario.facts)
    mode = GROUNDED_MODE if grounded else FREEFORM_MODE
    structure = structure_metrics(run.markdown, run.style_id, run.excluded_sections)

    if not run.succeeded:
        return Scorecard(
            run_id=run.run_id,
            transcript_id=run.transcript_id,
            variant_id=run.variant_id,
            style_id=run.style_id,
            mode=mode,
            judge_model=settings.model_name,
            structure=structure,
            fact_verdicts=tuple(
                FactVerdict(fact.fact_id, STATUS_MISSING, "The run produced no notes.")
                for fact in (scenario.facts if scenario else ())
            ),
            notes="The run produced no notes, so nothing could be graded.",
            error=run.error or "The run produced no notes.",
        )

    emit(0.05, "Checking structure…")
    model = LabOllama(
        settings.model_name,
        num_ctx=settings.num_ctx,
        temperature=settings.temperature,
        cancel_event=cancel_event,
        client=client,
    )

    if grounded:
        system = get_lab_prompt("judge_grounded")
        prompt = _grounded_prompt(scenario, run.markdown)
    else:
        from speaker_transcriber.promptlab.generator import summary_source_for

        budget = int(settings.num_ctx * CHARS_PER_TOKEN * TRANSCRIPT_BUDGET_FRACTION) - len(
            run.markdown
        )
        system = get_lab_prompt("judge_reference_free")
        prompt = _reference_free_prompt(summary_source_for(transcript), run.markdown, budget)

    emit(0.2, f"Judging with {settings.model_name}…")
    raw = model.generate(prompt, system=system, num_predict=2400)

    try:
        payload = parse_judge_json(raw)
    except (ValueError, json.JSONDecodeError) as first_error:
        LOGGER.warning("Judge returned unparseable output; asking once for a repair")
        emit(0.7, "Judge output was not valid JSON; retrying…")
        try:
            repaired = model.generate(
                "The response below was supposed to be a single JSON object and was not. "
                "Return the same content as one valid JSON object, with no prose, no "
                "explanation, and no code fence.\n\n" + raw,
                num_predict=2400,
                temperature=0.0,
            )
            payload = parse_judge_json(repaired)
        except Exception as second_error:
            LOGGER.warning("Judge repair failed: %s", second_error)
            return Scorecard(
                run_id=run.run_id,
                transcript_id=run.transcript_id,
                variant_id=run.variant_id,
                style_id=run.style_id,
                mode=mode,
                judge_model=settings.model_name,
                structure=structure,
                notes="The judge did not return usable JSON.",
                error=f"Unparseable judge output: {first_error}",
            )

    emit(0.9, "Scoring…")
    rubric = _rubric_from(payload)
    verdicts = _fact_verdicts(payload, scenario if grounded else None)
    unsupported = _string_list(payload, "unsupported_claims")
    distractor_hits = _string_list(payload, "asserted_distractors")
    recall = recall_for(scenario, verdicts) if grounded else 0.0
    precision = precision_for(run.markdown, unsupported, distractor_hits)

    notes = str(payload.get("notes") or "").strip()
    missing_points = _string_list(payload, "missing_points")
    if missing_points and not grounded:
        notes = (notes + "\n\nDropped: " + "; ".join(missing_points[:6])).strip()

    scorecard = Scorecard(
        run_id=run.run_id,
        transcript_id=run.transcript_id,
        variant_id=run.variant_id,
        style_id=run.style_id,
        mode=mode,
        judge_model=settings.model_name,
        recall=recall,
        precision=precision,
        composite=composite_for(mode, recall, precision, rubric, structure),
        rubric=rubric,
        structure=structure,
        fact_verdicts=verdicts,
        unsupported_claims=unsupported,
        asserted_distractors=distractor_hits,
        notes=notes,
    )
    emit(1.0, "Judging complete")
    return scorecard
