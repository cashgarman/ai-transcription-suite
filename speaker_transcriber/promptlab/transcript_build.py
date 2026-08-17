"""Turn generated dialogue into a real `TranscriptResult`.

The lab feeds summaries through the same `render_summary_source` path the app
uses, so a synthetic transcript has to be a genuine `TranscriptResult` with
speaker ids, display names, word timings, and the occasional overlap — not a
blob of text that merely looks like one.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any

from speaker_transcriber.export.json_exporter import from_json_dict, to_json_dict
from speaker_transcriber.pipeline.types import TranscriptResult, TranscriptSegment, Word
from speaker_transcriber.promptlab.types import Scenario


WORDS_PER_SECOND = 2.6
"""Conversational pace; turns a word count into a plausible duration."""

MIN_TURN_SECONDS = 1.2

GAP_RANGE = (0.15, 1.1)

OVERLAP_CHANCE = {"clean": 0.0, "light": 0.04, "heavy": 0.12}

_SPEAKER_LINE = re.compile(
    r"""^\s*
    (?:[-*>]\s*)?                 # stray list or quote marker
    \**\[?                        # optional bold / bracket wrapper
    (?P<name>[^:\[\]\n]{1,60}?)
    \]?\**
    \s*:\s*
    (?P<text>.+)$
    """,
    re.VERBOSE,
)

_STAGE_DIRECTION = re.compile(r"^\s*[\(\[][^)\]]*[\)\]]\s*$")


@dataclass(frozen=True)
class DialogueLine:
    speaker_id: str
    name: str
    text: str


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _name_index(scenario: Scenario) -> dict[str, str]:
    """Every reasonable way the model might write a participant's name."""
    index: dict[str, str] = {}
    for person in scenario.participants:
        keys = {person.name, person.speaker_id, person.name.split(" ")[0]}
        keys.add(person.speaker_id.replace("_", " "))
        for key in keys:
            normalized = _normalize_name(key)
            if normalized:
                index.setdefault(normalized, person.speaker_id)
    return index


def parse_dialogue(text: str, scenario: Scenario) -> list[DialogueLine]:
    """Split `Name: line` dialogue into turns, dropping anything unattributed.

    A model occasionally emits headings, stage directions, or a stray narrator
    line. Those are discarded rather than guessed at: an unattributed line in a
    speaker-diarized transcript would be a lie about who said what.
    """
    index = _name_index(scenario)
    fallback = scenario.participants[0].speaker_id if scenario.participants else "SPEAKER_00"
    lines: list[DialogueLine] = []
    display = {person.speaker_id: person.name for person in scenario.participants}

    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or _STAGE_DIRECTION.match(stripped):
            continue
        match = _SPEAKER_LINE.match(stripped)
        if not match:
            # A continuation of the previous turn, if there is one.
            if lines:
                previous = lines[-1]
                lines[-1] = DialogueLine(
                    previous.speaker_id,
                    previous.name,
                    f"{previous.text} {stripped}".strip(),
                )
            continue
        name = match.group("name").strip()
        body = match.group("text").strip()
        if not body:
            continue
        speaker_id = index.get(_normalize_name(name))
        if speaker_id is None:
            # An unknown name is usually a mangled spelling of a real one.
            speaker_id = _closest_speaker(name, index) or fallback
        lines.append(DialogueLine(speaker_id, display.get(speaker_id, name), body))
    return lines


def _closest_speaker(name: str, index: dict[str, str]) -> str | None:
    normalized = _normalize_name(name)
    if not normalized:
        return None
    for key, speaker_id in index.items():
        if key and (key in normalized or normalized in key):
            return speaker_id
    return None


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("*", "")).strip()


def _words_for(text: str, start: float, end: float, speaker: str) -> list[Word]:
    tokens = text.split()
    if not tokens:
        return []
    span = max(end - start, 0.1) / len(tokens)
    return [
        Word(
            word=token,
            start=round(start + index * span, 3),
            end=round(start + (index + 1) * span, 3),
            speaker=speaker,
        )
        for index, token in enumerate(tokens)
    ]


def build_transcript_result(
    scenario: Scenario,
    lines: list[DialogueLine],
    *,
    source_name: str = "",
    seed: int | None = None,
) -> TranscriptResult:
    """Assemble timed segments from dialogue turns."""
    rng = random.Random(seed if seed is not None else scenario.seed)
    overlap_chance = OVERLAP_CHANCE.get(scenario.disfluency, 0.04)

    segments: list[TranscriptSegment] = []
    clock = round(rng.uniform(0.0, 2.5), 2)
    previous_speaker = ""

    for line in lines:
        text = _clean_text(line.text)
        if not text:
            continue
        word_count = max(1, len(text.split()))
        duration = max(MIN_TURN_SECONDS, word_count / WORDS_PER_SECOND)
        start = round(clock, 3)
        end = round(start + duration, 3)
        overlapping: list[str] = []
        if (
            previous_speaker
            and previous_speaker != line.speaker_id
            and rng.random() < overlap_chance
        ):
            overlapping = [previous_speaker]
        segments.append(
            TranscriptSegment(
                start=start,
                end=end,
                speaker=line.speaker_id,
                text=text,
                words=_words_for(text, start, end, line.speaker_id),
                overlapping_speakers=overlapping,
            )
        )
        clock = end + rng.uniform(*GAP_RANGE)
        previous_speaker = line.speaker_id

    used = {segment.speaker for segment in segments}
    speakers = {
        person.speaker_id: person.name
        for person in scenario.participants
        if person.speaker_id in used
    }
    speaker_genders = {
        person.speaker_id: person.gender
        for person in scenario.participants
        if person.speaker_id in used
    }
    name = source_name or f"{scenario.meeting_kind}-{scenario.seed}.wav"

    return TranscriptResult(
        source_file=name,
        language="en",
        duration_seconds=round(segments[-1].end, 3) if segments else 0.0,
        speakers=speakers,
        speaker_genders=speaker_genders,
        segments=segments,
        alignment_available=True,
        diarization_available=True,
        source_files=[name],
    )


def result_to_payload(result: TranscriptResult) -> dict[str, Any]:
    return to_json_dict(result)


def result_from_payload(payload: dict[str, Any]) -> TranscriptResult:
    return from_json_dict(payload)


def transcript_word_count(result: TranscriptResult) -> int:
    return sum(len(segment.text.split()) for segment in result.segments)
