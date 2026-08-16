"""Prompt Lab: a closed evaluation loop for the summarization prompts.

Synthetic transcripts go in, summaries come out under swappable prompt
variants, a local judge model and a set of deterministic checks score them, a
human breaks ties in blinded A/B comparisons, and an optimizer model turns all
of that evidence into new candidate prompts.

Submodules that talk to Ollama import it lazily, so importing this package
stays cheap and safe when the daemon is not running.
"""

from __future__ import annotations

from speaker_transcriber.promptlab.store import LabStore
from speaker_transcriber.promptlab.types import (
    ABPair,
    Distractor,
    Fact,
    FactVerdict,
    FREEFORM_MODE,
    GeneratedTranscript,
    GENERATION_MODES,
    GROUNDED_MODE,
    HumanVerdict,
    OptimizerCandidate,
    Participant,
    PROMPT_STAGES,
    PromptVariant,
    RubricScores,
    Scenario,
    Scorecard,
    SHIPPED_VARIANT_ID,
    StructureMetrics,
    SummaryRun,
    Topic,
    VariantStanding,
    WINNER_LEFT,
    WINNER_RIGHT,
    WINNER_TIE,
)


__all__ = [
    "ABPair",
    "Distractor",
    "FREEFORM_MODE",
    "Fact",
    "FactVerdict",
    "GENERATION_MODES",
    "GROUNDED_MODE",
    "GeneratedTranscript",
    "HumanVerdict",
    "LabStore",
    "OptimizerCandidate",
    "PROMPT_STAGES",
    "Participant",
    "PromptVariant",
    "RubricScores",
    "SHIPPED_VARIANT_ID",
    "Scenario",
    "Scorecard",
    "StructureMetrics",
    "SummaryRun",
    "Topic",
    "VariantStanding",
    "WINNER_LEFT",
    "WINNER_RIGHT",
    "WINNER_TIE",
]
