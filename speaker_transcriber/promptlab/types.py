"""Records the Prompt Lab writes to disk.

Every record carries the inputs that produced it — seed, model, context length,
style, and the fingerprint of the prompt variant in force — so any number in a
leaderboard can be traced back to a reproducible run.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


GROUNDED_MODE = "grounded"
"""Transcript rendered from a procedural scenario with known ground truth."""

FREEFORM_MODE = "freeform"
"""Transcript improvised by the generator model from a topic seed only."""

GENERATION_MODES = (GROUNDED_MODE, FREEFORM_MODE)

FACT_KINDS = (
    "decision",
    "action_item",
    "risk",
    "open_question",
    "metric",
    "deadline",
)

SALIENCE_LEVELS = ("core", "secondary", "incidental")

SALIENCE_WEIGHTS = {"core": 3.0, "secondary": 2.0, "incidental": 1.0}

DISFLUENCY_LEVELS = ("clean", "light", "heavy")

STATUS_COVERED = "covered"
STATUS_PARTIAL = "partial"
STATUS_MISSING = "missing"
FACT_STATUSES = (STATUS_COVERED, STATUS_PARTIAL, STATUS_MISSING)

STATUS_CREDIT = {STATUS_COVERED: 1.0, STATUS_PARTIAL: 0.5, STATUS_MISSING: 0.0}

WINNER_LEFT = "left"
WINNER_RIGHT = "right"
WINNER_TIE = "tie"
WINNERS = (WINNER_LEFT, WINNER_RIGHT, WINNER_TIE)

SHIPPED_VARIANT_ID = "shipped"
"""The variant that resolves to the prompt files the app actually ships."""

PROMPT_STAGES = ("system", "chunk", "merge", "validate", "format")

AUTHOR_SHIPPED = "shipped"
AUTHOR_HUMAN = "human"
AUTHOR_OPTIMIZER = "optimizer"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    """A sortable, collision-resistant id: prefix, UTC stamp, short random tail."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:6]}"


def fingerprint(payload: Mapping[str, str]) -> str:
    digest = hashlib.sha256()
    for key in sorted(payload):
        digest.update(key.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(str(payload[key]).encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()[:16]


def _strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


@dataclass(frozen=True)
class Participant:
    speaker_id: str
    name: str
    role: str
    speaking_style: str = "plain"
    verbosity: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Participant:
        return cls(
            speaker_id=_text(data.get("speaker_id")),
            name=_text(data.get("name")),
            role=_text(data.get("role")),
            speaking_style=_text(data.get("speaking_style"), "plain"),
            verbosity=_float(data.get("verbosity"), 0.5),
        )


@dataclass(frozen=True)
class Topic:
    topic_id: str
    title: str
    intent: str
    minutes: int = 5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Topic:
        return cls(
            topic_id=_text(data.get("topic_id")),
            title=_text(data.get("title")),
            intent=_text(data.get("intent")),
            minutes=_int(data.get("minutes"), 5),
        )


@dataclass(frozen=True)
class Fact:
    """One thing a faithful summary of the meeting has to carry."""

    fact_id: str
    kind: str
    text: str
    topic_id: str
    owner: str = ""
    salience: str = "core"

    @property
    def weight(self) -> float:
        return SALIENCE_WEIGHTS.get(self.salience, 1.0)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Fact:
        return cls(
            fact_id=_text(data.get("fact_id")),
            kind=_text(data.get("kind"), "decision"),
            text=_text(data.get("text")),
            topic_id=_text(data.get("topic_id")),
            owner=_text(data.get("owner")),
            salience=_text(data.get("salience"), "core"),
        )


@dataclass(frozen=True)
class Distractor:
    """Something said in the room that must NOT be reported as settled fact."""

    distractor_id: str
    text: str
    topic_id: str
    reason: str = "retracted"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Distractor:
        return cls(
            distractor_id=_text(data.get("distractor_id")),
            text=_text(data.get("text")),
            topic_id=_text(data.get("topic_id")),
            reason=_text(data.get("reason"), "retracted"),
        )


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    seed: int
    mode: str
    style_id: str
    meeting_kind: str
    title: str
    duration_minutes: int
    disfluency: str
    participants: tuple[Participant, ...] = ()
    topics: tuple[Topic, ...] = ()
    facts: tuple[Fact, ...] = ()
    distractors: tuple[Distractor, ...] = ()
    created_at: str = field(default_factory=utcnow_iso)

    @property
    def is_grounded(self) -> bool:
        return self.mode == GROUNDED_MODE

    @property
    def total_weight(self) -> float:
        return sum(fact.weight for fact in self.facts)

    def facts_for_topic(self, topic_id: str) -> tuple[Fact, ...]:
        return tuple(fact for fact in self.facts if fact.topic_id == topic_id)

    def distractors_for_topic(self, topic_id: str) -> tuple[Distractor, ...]:
        return tuple(item for item in self.distractors if item.topic_id == topic_id)

    def fact_by_id(self, fact_id: str) -> Fact | None:
        return next((fact for fact in self.facts if fact.fact_id == fact_id), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "seed": self.seed,
            "mode": self.mode,
            "style_id": self.style_id,
            "meeting_kind": self.meeting_kind,
            "title": self.title,
            "duration_minutes": self.duration_minutes,
            "disfluency": self.disfluency,
            "participants": [item.to_dict() for item in self.participants],
            "topics": [item.to_dict() for item in self.topics],
            "facts": [item.to_dict() for item in self.facts],
            "distractors": [item.to_dict() for item in self.distractors],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Scenario:
        return cls(
            scenario_id=_text(data.get("scenario_id")),
            seed=_int(data.get("seed")),
            mode=_text(data.get("mode"), GROUNDED_MODE),
            style_id=_text(data.get("style_id")),
            meeting_kind=_text(data.get("meeting_kind")),
            title=_text(data.get("title")),
            duration_minutes=_int(data.get("duration_minutes"), 30),
            disfluency=_text(data.get("disfluency"), "light"),
            participants=tuple(
                Participant.from_dict(item) for item in data.get("participants") or ()
            ),
            topics=tuple(Topic.from_dict(item) for item in data.get("topics") or ()),
            facts=tuple(Fact.from_dict(item) for item in data.get("facts") or ()),
            distractors=tuple(
                Distractor.from_dict(item) for item in data.get("distractors") or ()
            ),
            created_at=_text(data.get("created_at"), utcnow_iso()),
        )


@dataclass(frozen=True)
class GeneratedTranscript:
    """A synthetic transcript plus the payload of its `TranscriptResult`."""

    transcript_id: str
    scenario_id: str
    seed: int
    mode: str
    style_id: str
    label: str
    generator_model: str
    generator_num_ctx: int
    duration_seconds: float
    word_count: int
    transcript: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GeneratedTranscript:
        return cls(
            transcript_id=_text(data.get("transcript_id")),
            scenario_id=_text(data.get("scenario_id")),
            seed=_int(data.get("seed")),
            mode=_text(data.get("mode"), GROUNDED_MODE),
            style_id=_text(data.get("style_id")),
            label=_text(data.get("label")),
            generator_model=_text(data.get("generator_model")),
            generator_num_ctx=_int(data.get("generator_num_ctx")),
            duration_seconds=_float(data.get("duration_seconds")),
            word_count=_int(data.get("word_count")),
            transcript=dict(data.get("transcript") or {}),
            created_at=_text(data.get("created_at"), utcnow_iso()),
        )


@dataclass(frozen=True)
class PromptVariant:
    """A candidate prompt pack for one style.

    ``stages`` holds only the stages this variant overrides; anything absent
    falls through to the shipped prompt file at resolve time, which keeps a
    single-stage experiment from freezing copies of the other four.
    """

    variant_id: str
    style_id: str
    label: str
    author: str = AUTHOR_HUMAN
    parent_id: str = SHIPPED_VARIANT_ID
    rationale: str = ""
    stages: dict[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=utcnow_iso)

    @property
    def is_shipped(self) -> bool:
        return self.variant_id == SHIPPED_VARIANT_ID

    @property
    def overridden_stages(self) -> tuple[str, ...]:
        return tuple(stage for stage in PROMPT_STAGES if self.stages.get(stage))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PromptVariant:
        stages = {
            str(key): str(value)
            for key, value in (data.get("stages") or {}).items()
            if str(key) in PROMPT_STAGES and str(value).strip()
        }
        return cls(
            variant_id=_text(data.get("variant_id")),
            style_id=_text(data.get("style_id")),
            label=_text(data.get("label")),
            author=_text(data.get("author"), AUTHOR_HUMAN),
            parent_id=_text(data.get("parent_id"), SHIPPED_VARIANT_ID),
            rationale=_text(data.get("rationale")),
            stages=stages,
            created_at=_text(data.get("created_at"), utcnow_iso()),
        )


@dataclass(frozen=True)
class SummaryRun:
    run_id: str
    transcript_id: str
    scenario_id: str
    variant_id: str
    variant_fingerprint: str
    style_id: str
    model_name: str
    num_ctx: int
    markdown: str = ""
    excluded_sections: tuple[str, ...] = ()
    omit_speaker_names: bool = False
    elapsed_seconds: float = 0.0
    error: str = ""
    created_at: str = field(default_factory=utcnow_iso)

    @property
    def succeeded(self) -> bool:
        return not self.error and bool(self.markdown.strip())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SummaryRun:
        return cls(
            run_id=_text(data.get("run_id")),
            transcript_id=_text(data.get("transcript_id")),
            scenario_id=_text(data.get("scenario_id")),
            variant_id=_text(data.get("variant_id"), SHIPPED_VARIANT_ID),
            variant_fingerprint=_text(data.get("variant_fingerprint")),
            style_id=_text(data.get("style_id")),
            model_name=_text(data.get("model_name")),
            num_ctx=_int(data.get("num_ctx")),
            markdown=_text(data.get("markdown")),
            excluded_sections=_strings(data.get("excluded_sections")),
            omit_speaker_names=bool(data.get("omit_speaker_names")),
            elapsed_seconds=_float(data.get("elapsed_seconds")),
            error=_text(data.get("error")),
            created_at=_text(data.get("created_at"), utcnow_iso()),
        )


@dataclass(frozen=True)
class FactVerdict:
    fact_id: str
    status: str
    evidence: str = ""

    @property
    def credit(self) -> float:
        return STATUS_CREDIT.get(self.status, 0.0)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FactVerdict:
        status = _text(data.get("status"), STATUS_MISSING).strip().lower()
        return cls(
            fact_id=_text(data.get("fact_id")),
            status=status if status in FACT_STATUSES else STATUS_MISSING,
            evidence=_text(data.get("evidence")),
        )


@dataclass(frozen=True)
class StructureMetrics:
    """Checks that need no model: headings, tables, and size."""

    expected_headings: tuple[str, ...] = ()
    missing_headings: tuple[str, ...] = ()
    leaked_headings: tuple[str, ...] = ()
    has_action_table: bool = False
    action_table_required: bool = False
    heading_count: int = 0
    word_count: int = 0

    @property
    def score(self) -> float:
        penalties = 0.0
        if self.expected_headings:
            penalties += len(self.missing_headings) / len(self.expected_headings)
        if self.leaked_headings:
            penalties += 1.0
        if self.action_table_required and not self.has_action_table:
            penalties += 0.5
        return max(0.0, 1.0 - penalties)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StructureMetrics:
        return cls(
            expected_headings=_strings(data.get("expected_headings")),
            missing_headings=_strings(data.get("missing_headings")),
            leaked_headings=_strings(data.get("leaked_headings")),
            has_action_table=bool(data.get("has_action_table")),
            action_table_required=bool(data.get("action_table_required")),
            heading_count=_int(data.get("heading_count")),
            word_count=_int(data.get("word_count")),
        )


RUBRIC_DIMENSIONS = (
    "faithfulness",
    "coverage",
    "structure",
    "attribution",
    "concision",
    "actionability",
)


@dataclass(frozen=True)
class RubricScores:
    """Judge scores, each 1 to 5."""

    faithfulness: float = 0.0
    coverage: float = 0.0
    structure: float = 0.0
    attribution: float = 0.0
    concision: float = 0.0
    actionability: float = 0.0

    @property
    def mean(self) -> float:
        values = [getattr(self, name) for name in RUBRIC_DIMENSIONS]
        return sum(values) / len(values) if values else 0.0

    @property
    def normalized(self) -> float:
        """The mean rescaled from the 1-5 rubric onto 0-1."""
        return max(0.0, min(1.0, (self.mean - 1.0) / 4.0))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RubricScores:
        return cls(
            **{name: _float(data.get(name)) for name in RUBRIC_DIMENSIONS}
        )


@dataclass(frozen=True)
class Scorecard:
    run_id: str
    transcript_id: str
    variant_id: str
    style_id: str
    mode: str
    judge_model: str
    recall: float = 0.0
    precision: float = 0.0
    composite: float = 0.0
    rubric: RubricScores = field(default_factory=RubricScores)
    structure: StructureMetrics = field(default_factory=StructureMetrics)
    fact_verdicts: tuple[FactVerdict, ...] = ()
    unsupported_claims: tuple[str, ...] = ()
    asserted_distractors: tuple[str, ...] = ()
    notes: str = ""
    error: str = ""
    created_at: str = field(default_factory=utcnow_iso)

    def missing_fact_ids(self) -> tuple[str, ...]:
        return tuple(
            verdict.fact_id
            for verdict in self.fact_verdicts
            if verdict.status != STATUS_COVERED
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "transcript_id": self.transcript_id,
            "variant_id": self.variant_id,
            "style_id": self.style_id,
            "mode": self.mode,
            "judge_model": self.judge_model,
            "recall": self.recall,
            "precision": self.precision,
            "composite": self.composite,
            "rubric": self.rubric.to_dict(),
            "structure": self.structure.to_dict(),
            "fact_verdicts": [item.to_dict() for item in self.fact_verdicts],
            "unsupported_claims": list(self.unsupported_claims),
            "asserted_distractors": list(self.asserted_distractors),
            "notes": self.notes,
            "error": self.error,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Scorecard:
        return cls(
            run_id=_text(data.get("run_id")),
            transcript_id=_text(data.get("transcript_id")),
            variant_id=_text(data.get("variant_id")),
            style_id=_text(data.get("style_id")),
            mode=_text(data.get("mode"), GROUNDED_MODE),
            judge_model=_text(data.get("judge_model")),
            recall=_float(data.get("recall")),
            precision=_float(data.get("precision")),
            composite=_float(data.get("composite")),
            rubric=RubricScores.from_dict(data.get("rubric") or {}),
            structure=StructureMetrics.from_dict(data.get("structure") or {}),
            fact_verdicts=tuple(
                FactVerdict.from_dict(item) for item in data.get("fact_verdicts") or ()
            ),
            unsupported_claims=_strings(data.get("unsupported_claims")),
            asserted_distractors=_strings(data.get("asserted_distractors")),
            notes=_text(data.get("notes")),
            error=_text(data.get("error")),
            created_at=_text(data.get("created_at"), utcnow_iso()),
        )


@dataclass(frozen=True)
class ABPair:
    """Two runs over the same transcript, differing only in prompt variant."""

    pair_id: str
    transcript_id: str
    style_id: str
    left_run_id: str
    right_run_id: str
    left_variant_id: str
    right_variant_id: str
    created_at: str = field(default_factory=utcnow_iso)

    def run_id_for(self, side: str) -> str:
        return self.left_run_id if side == WINNER_LEFT else self.right_run_id

    def variant_id_for(self, side: str) -> str:
        return self.left_variant_id if side == WINNER_LEFT else self.right_variant_id

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ABPair:
        return cls(
            pair_id=_text(data.get("pair_id")),
            transcript_id=_text(data.get("transcript_id")),
            style_id=_text(data.get("style_id")),
            left_run_id=_text(data.get("left_run_id")),
            right_run_id=_text(data.get("right_run_id")),
            left_variant_id=_text(data.get("left_variant_id")),
            right_variant_id=_text(data.get("right_variant_id")),
            created_at=_text(data.get("created_at"), utcnow_iso()),
        )


VERDICT_TAGS = (
    "missed_facts",
    "hallucinated",
    "wrong_owner",
    "too_long",
    "too_terse",
    "bad_structure",
    "weak_actions",
    "tone_off",
)


@dataclass(frozen=True)
class HumanVerdict:
    pair_id: str
    winner: str
    tags: tuple[str, ...] = ()
    notes: str = ""
    created_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> HumanVerdict:
        winner = _text(data.get("winner"), WINNER_TIE).strip().lower()
        return cls(
            pair_id=_text(data.get("pair_id")),
            winner=winner if winner in WINNERS else WINNER_TIE,
            tags=_strings(data.get("tags")),
            notes=_text(data.get("notes")),
            created_at=_text(data.get("created_at"), utcnow_iso()),
        )


@dataclass(frozen=True)
class OptimizerCandidate:
    candidate_id: str
    style_id: str
    stage: str
    base_variant_id: str
    prompt_text: str
    changelog: str = ""
    evidence_digest: str = ""
    model_name: str = ""
    saved_variant_id: str = ""
    created_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> OptimizerCandidate:
        return cls(
            candidate_id=_text(data.get("candidate_id")),
            style_id=_text(data.get("style_id")),
            stage=_text(data.get("stage")),
            base_variant_id=_text(data.get("base_variant_id"), SHIPPED_VARIANT_ID),
            prompt_text=_text(data.get("prompt_text")),
            changelog=_text(data.get("changelog")),
            evidence_digest=_text(data.get("evidence_digest")),
            model_name=_text(data.get("model_name")),
            saved_variant_id=_text(data.get("saved_variant_id")),
            created_at=_text(data.get("created_at"), utcnow_iso()),
        )


@dataclass(frozen=True)
class VariantStanding:
    """Aggregated standing of one variant on the leaderboard."""

    variant_id: str
    label: str = ""
    runs: int = 0
    wins: int = 0
    losses: int = 0
    ties: int = 0
    elo: float = 1500.0
    mean_composite: float = 0.0
    mean_recall: float = 0.0
    mean_precision: float = 0.0
    mean_rubric: float = 0.0

    @property
    def decided(self) -> int:
        return self.wins + self.losses

    @property
    def win_rate(self) -> float:
        played = self.wins + self.losses + self.ties
        if not played:
            return 0.0
        return (self.wins + 0.5 * self.ties) / played

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_tags(tags: Iterable[str]) -> tuple[str, ...]:
    """Known verdict tags only, in registry order, without duplicates."""
    chosen = {str(tag) for tag in tags or ()}
    return tuple(tag for tag in VERDICT_TAGS if tag in chosen)
