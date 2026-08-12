from __future__ import annotations

import re

from speaker_transcriber.pipeline.types import TranscriptSegment, Word


def _join_words(words: list[Word]) -> str:
    text = " ".join(word.word.strip() for word in words if word.word.strip())
    text = re.sub(r"\s+([,.;:!?%])", r"\1", text)
    text = re.sub(r"([(\[]) ", r"\1", text)
    return text.strip()


def _make_segment(words: list[Word]) -> TranscriptSegment:
    overlapping = sorted(
        {
            speaker
            for word in words
            for speaker in word.overlapping_speakers
            if speaker != words[0].speaker
        }
    )
    return TranscriptSegment(
        start=words[0].start,
        end=words[-1].end,
        speaker=words[0].speaker,
        text=_join_words(words),
        words=list(words),
        overlapping_speakers=overlapping,
        uncertain=any(word.uncertain for word in words),
    )


def merge_words(
    words: list[Word],
    gap_threshold_seconds: float = 0.5,
    max_duration_seconds: float = 30.0,
) -> list[TranscriptSegment]:
    if not words:
        return []
    blocks: list[TranscriptSegment] = []
    current = [words[0]]
    for word in words[1:]:
        gap = max(0.0, word.start - current[-1].end)
        prospective_duration = word.end - current[0].start
        should_merge = (
            word.speaker == current[0].speaker
            and gap <= gap_threshold_seconds
            and prospective_duration <= max_duration_seconds
        )
        if should_merge:
            current.append(word)
        else:
            blocks.append(_make_segment(current))
            current = [word]
    blocks.append(_make_segment(current))
    return blocks
