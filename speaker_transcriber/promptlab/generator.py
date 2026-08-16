"""Turn a scenario into a synthetic transcript.

Generation runs one topic at a time. A single call asked to produce a whole
meeting drifts: it forgets the middle of its instructions, drops the planted
facts, and settles into a rhythm of tidy alternating turns. Per-topic calls keep
each instruction list short enough that the planted facts actually survive,
which is the entire point of the grounded mode.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from speaker_transcriber.promptlab.lab_prompts import get_lab_prompt
from speaker_transcriber.promptlab.ollama_client import LabOllama
from speaker_transcriber.promptlab.transcript_build import (
    DialogueLine,
    build_transcript_result,
    parse_dialogue,
    result_to_payload,
    transcript_word_count,
)
from speaker_transcriber.promptlab.types import (
    GROUNDED_MODE,
    GeneratedTranscript,
    Scenario,
    new_id,
)


LOGGER = logging.getLogger("speaker_transcriber.promptlab.generator")

WORDS_PER_MINUTE = 130
"""Spoken words per minute, used to size each topic's generation budget."""

TOKENS_PER_WORD = 2.0

MIN_TOPIC_WORDS = 150

DISFLUENCY_NOTES = {
    "clean": (
        "Keep the speech tidy. Complete sentences, few fillers, no cross-talk. "
        "People still interrupt each other's reasoning, but not their words."
    ),
    "light": (
        "Natural speech: occasional fillers, a few false starts, one or two "
        "sentences that trail off and get picked up again."
    ),
    "heavy": (
        "Messy speech, the way a real recording sounds. Frequent fillers, "
        "abandoned sentences, people talking over each other, a couple of "
        "words that a transcription system would plausibly mishear and render "
        "as the wrong similar-sounding word."
    ),
}


@dataclass(frozen=True)
class GenerationSettings:
    model_name: str
    num_ctx: int = 8192
    temperature: float = 0.85
    words_per_minute: int = WORDS_PER_MINUTE


ProgressFn = Callable[[float, str], None]


def _participants_block(scenario: Scenario) -> str:
    lines = []
    for person in scenario.participants:
        share = "talks a lot" if person.verbosity > 0.7 else (
            "says little" if person.verbosity < 0.4 else "speaks a normal amount"
        )
        lines.append(f"- {person.name} ({person.role}): {person.speaking_style}; {share}.")
    return "\n".join(lines)


def _facts_block(scenario: Scenario, topic_id: str) -> str:
    facts = scenario.facts_for_topic(topic_id)
    if not facts:
        return "- (nothing specific; let the conversation find its own substance)"
    lines = []
    for fact in facts:
        owner = f" [{fact.owner} is the one who takes this on]" if fact.owner else ""
        lines.append(f"- ({fact.kind}) {fact.text}{owner}")
    return "\n".join(lines)


def _distractors_block(scenario: Scenario, topic_id: str) -> str:
    items = scenario.distractors_for_topic(topic_id)
    if not items:
        return ""
    lines = [f"- {item.text}" for item in items]
    return "\n".join(lines)


def _topic_prompt(scenario: Scenario, topic_index: int, target_words: int) -> str:
    topic = scenario.topics[topic_index]
    earlier = [item.title for item in scenario.topics[:topic_index]]
    later = [item.title for item in scenario.topics[topic_index + 1 :]]

    sections = [
        f"# Meeting\n\n{scenario.title} — a {scenario.meeting_kind.replace('_', ' ')} "
        f"running about {scenario.duration_minutes} minutes.",
        f"# People in the room\n\n{_participants_block(scenario)}",
        f"# This segment\n\n{topic.title}. {topic.intent}",
    ]
    if earlier:
        sections.append(
            "# Already covered earlier in the meeting\n\n"
            + "\n".join(f"- {title}" for title in earlier)
            + "\n\nDo not re-open these. A passing reference is fine."
        )
    if later:
        sections.append(
            "# Still to come after this segment\n\n"
            + "\n".join(f"- {title}" for title in later)
            + "\n\nDo not cover these yet."
        )
    if scenario.is_grounded:
        sections.append(f"# Must be established\n\n{_facts_block(scenario, topic.topic_id)}")
        dropped = _distractors_block(scenario, topic.topic_id)
        if dropped:
            sections.append(f"# Raised and dropped\n\n{dropped}")
    sections.append(
        "# How it should sound\n\n"
        + DISFLUENCY_NOTES.get(scenario.disfluency, DISFLUENCY_NOTES["light"])
    )
    sections.append(
        f"# Length\n\nAbout {target_words} words of dialogue for this segment.\n\n"
        "Begin the dialogue now. Nothing but `Name: line` turns."
    )
    if topic_index == 0:
        sections.append(
            "This is the start of the meeting, so open the way a real one opens: "
            "somebody kicks it off mid-thought, not with a formal welcome."
        )
    return "\n\n".join(sections)


def _topic_word_targets(scenario: Scenario, settings: GenerationSettings) -> list[int]:
    if not scenario.topics:
        return []
    total = max(len(scenario.topics) * MIN_TOPIC_WORDS, scenario.duration_minutes * settings.words_per_minute)
    minutes = [max(1, topic.minutes) for topic in scenario.topics]
    span = sum(minutes)
    return [max(MIN_TOPIC_WORDS, round(total * portion / span)) for portion in minutes]


def generate_transcript(
    scenario: Scenario,
    settings: GenerationSettings,
    *,
    on_progress: ProgressFn | None = None,
    on_chunk: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
    client: Any = None,
) -> GeneratedTranscript:
    """Render `scenario` into a transcript, one topic at a time."""
    if not scenario.topics:
        raise ValueError("The scenario has no topics to render.")

    model = LabOllama(
        settings.model_name,
        num_ctx=settings.num_ctx,
        temperature=settings.temperature,
        cancel_event=cancel_event,
        client=client,
    )
    system = get_lab_prompt(
        "scenario_dialogue" if scenario.is_grounded else "freeform_transcript"
    )
    targets = _topic_word_targets(scenario, settings)

    def emit(fraction: float, message: str) -> None:
        if on_progress is not None:
            on_progress(min(max(fraction, 0.0), 1.0), message)

    lines: list[DialogueLine] = []
    total = len(scenario.topics)
    for index, topic in enumerate(scenario.topics):
        model.raise_if_cancelled()
        emit(index / total, f"Writing segment {index + 1} of {total}: {topic.title}")
        target = targets[index]
        response = model.generate(
            _topic_prompt(scenario, index, target),
            system=system,
            num_predict=int(target * TOKENS_PER_WORD) + 256,
            on_chunk=on_chunk,
        )
        parsed = parse_dialogue(response, scenario)
        if not parsed:
            raise RuntimeError(
                f"The generator returned no usable dialogue for segment "
                f"'{topic.title}'. Check that {settings.model_name} follows the "
                f"`Name: line` format."
            )
        LOGGER.info(
            "Segment %d of %d produced %d turn(s) for '%s'",
            index + 1,
            total,
            len(parsed),
            topic.title,
        )
        lines.extend(parsed)
        emit((index + 1) / total, f"Completed segment {index + 1} of {total}")

    result = build_transcript_result(scenario, lines)
    payload = result_to_payload(result)
    emit(1.0, "Transcript complete")

    return GeneratedTranscript(
        transcript_id=new_id("txn"),
        scenario_id=scenario.scenario_id,
        seed=scenario.seed,
        mode=scenario.mode if scenario.mode else GROUNDED_MODE,
        style_id=scenario.style_id,
        label=scenario.title,
        generator_model=settings.model_name,
        generator_num_ctx=settings.num_ctx,
        duration_seconds=result.duration_seconds,
        word_count=transcript_word_count(result),
        transcript=payload,
    )


def summary_source_for(transcript: GeneratedTranscript) -> str:
    """The exact text the app would hand the summarizer for this transcript."""
    from speaker_transcriber.export.text_exporter import render_summary_source
    from speaker_transcriber.promptlab.transcript_build import result_from_payload

    return render_summary_source(result_from_payload(transcript.transcript))
