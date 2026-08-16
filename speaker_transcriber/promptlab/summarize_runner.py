"""Run one synthetic transcript through the real summarizer under one variant.

Nothing here reimplements summarization. The point of the lab is to measure the
code the app actually ships, so this builds a `RequirementsSummarizer` exactly
as the app does and only swaps in the variant's prompt text.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from speaker_transcriber.errors import ProcessingCancelled
from speaker_transcriber.promptlab.generator import summary_source_for
from speaker_transcriber.promptlab.promptset import variant_fingerprint, variant_overrides
from speaker_transcriber.promptlab.types import (
    GeneratedTranscript,
    PromptVariant,
    SummaryRun,
    new_id,
)


LOGGER = logging.getLogger("speaker_transcriber.promptlab.runner")


@dataclass(frozen=True)
class RunSettings:
    """Everything about a run that is not the transcript or the prompts."""

    model_name: str
    num_ctx: int
    excluded_sections: tuple[str, ...] = ()
    omit_speaker_names: bool = False


SummarizerFactory = Callable[..., Any]


def _default_factory(**kwargs: Any) -> Any:
    from speaker_transcriber.models.summarization import RequirementsSummarizer

    return RequirementsSummarizer(**kwargs)


def run_summary(
    transcript: GeneratedTranscript,
    variant: PromptVariant,
    settings: RunSettings,
    *,
    on_progress: Callable[[float, str], None] | None = None,
    on_chunk: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
    summarizer_factory: SummarizerFactory | None = None,
) -> SummaryRun:
    """Summarize `transcript` with `variant`'s prompts and record the result."""
    if variant.style_id != transcript.style_id:
        LOGGER.info(
            "Running style %s prompts against a transcript generated for %s",
            variant.style_id,
            transcript.style_id,
        )
    factory = summarizer_factory or _default_factory
    source = summary_source_for(transcript)
    started = time.monotonic()

    summarizer = factory(
        model_name=settings.model_name,
        num_ctx=settings.num_ctx,
        style=variant.style_id,
        excluded_sections=tuple(settings.excluded_sections),
        omit_speaker_names=settings.omit_speaker_names,
        cancel_event=cancel_event,
        prompt_overrides=variant_overrides(variant),
    )

    markdown = ""
    error = ""
    try:
        markdown = summarizer.summarize(
            source,
            on_progress=on_progress,
            on_chunk=on_chunk,
        )
    except ProcessingCancelled:
        raise
    except Exception as exc:
        # A failed run is still evidence: a prompt that makes the model produce
        # nothing usable should show up on the leaderboard, not vanish.
        LOGGER.exception("Prompt Lab run failed")
        error = str(exc)

    return SummaryRun(
        run_id=new_id("run"),
        transcript_id=transcript.transcript_id,
        scenario_id=transcript.scenario_id,
        variant_id=variant.variant_id,
        variant_fingerprint=variant_fingerprint(variant),
        style_id=variant.style_id,
        model_name=settings.model_name,
        num_ctx=settings.num_ctx,
        markdown=markdown,
        excluded_sections=tuple(settings.excluded_sections),
        omit_speaker_names=settings.omit_speaker_names,
        elapsed_seconds=round(time.monotonic() - started, 2),
        error=error,
    )
