from __future__ import annotations

from speaker_transcriber.pipeline.types import DiarizationSegment, RawSegment, Word


def _overlap(start: float, end: float, segment: DiarizationSegment) -> float:
    return max(0.0, min(end, segment.end) - max(start, segment.start))


def _distance(start: float, end: float, segment: DiarizationSegment) -> float:
    if end < segment.start:
        return segment.start - end
    if start > segment.end:
        return start - segment.end
    return 0.0


def assign_word(
    word: Word,
    diarization: list[DiarizationSegment],
    inherit_threshold_seconds: float,
) -> Word:
    if not diarization:
        return word
    midpoint = (word.start + word.end) / 2
    overlapping = [
        segment for segment in diarization if _overlap(word.start, word.end, segment) > 0
    ]
    containing = [
        segment for segment in diarization if segment.start <= midpoint <= segment.end
    ]

    if containing:
        primary = max(
            containing,
            key=lambda segment: (
                _overlap(word.start, word.end, segment),
                -(segment.end - segment.start),
            ),
        )
    elif overlapping:
        primary = max(
            overlapping,
            key=lambda segment: _overlap(word.start, word.end, segment),
        )
    else:
        nearest = min(
            diarization,
            key=lambda segment: _distance(word.start, word.end, segment),
        )
        primary = (
            nearest
            if _distance(word.start, word.end, nearest) <= inherit_threshold_seconds
            else None
        )

    if primary is None:
        return word

    additional = sorted(
        {
            segment.speaker
            for segment in overlapping
            if segment.speaker != primary.speaker
        }
    )
    duration = max(word.end - word.start, 0.001)
    uncertain = any(
        segment.speaker != primary.speaker
        and _overlap(word.start, word.end, segment) / duration >= 0.5
        for segment in overlapping
    )
    return Word(
        word=word.word,
        start=word.start,
        end=word.end,
        speaker=primary.speaker,
        overlapping_speakers=additional,
        uncertain=uncertain,
    )


def words_from_segments(segments: list[RawSegment]) -> list[Word]:
    words: list[Word] = []
    for segment in segments:
        if segment.words:
            for item in segment.words:
                value = str(item.get("word", "")).strip()
                if value and "start" in item and "end" in item:
                    words.append(
                        Word(
                            word=value,
                            start=float(item["start"]),
                            end=float(item["end"]),
                        )
                    )
        elif segment.text:
            words.append(
                Word(
                    word=segment.text.strip(),
                    start=segment.start,
                    end=segment.end,
                    uncertain=True,
                )
            )
    return words


def assign_speakers(
    segments: list[RawSegment],
    diarization: list[DiarizationSegment],
    inherit_threshold_seconds: float = 0.3,
) -> list[Word]:
    return [
        assign_word(word, diarization, inherit_threshold_seconds)
        for word in words_from_segments(segments)
    ]
