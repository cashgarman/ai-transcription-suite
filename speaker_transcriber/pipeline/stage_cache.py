from __future__ import annotations

from speaker_transcriber.pipeline.types import (
    DiarizationSegment,
    RawSegment,
    TranscriptResult,
)


def normalize_model_name(value: str | None) -> str:
    return str(value or "").strip().lower()


def cached_stage_model(result: TranscriptResult | None, key: str) -> str:
    if result is None:
        return ""
    config = result.fallback_config or {}
    return normalize_model_name(config.get(key))


def stage_model_changed(
    result: TranscriptResult | None,
    key: str,
    current: str | None,
) -> bool:
    """True when a cached run exists and `current` is a different model.

    Older caches that never recorded the stage model are treated as changed so
    the user can still re-run that stage from stored transcript work.
    """
    if result is None:
        return False
    selected = normalize_model_name(current)
    if not selected:
        return False
    cached = cached_stage_model(result, key)
    if not cached:
        return True
    return cached != selected


def copy_raw_segments(segments: list[RawSegment]) -> list[RawSegment]:
    return [
        RawSegment(
            start=segment.start,
            end=segment.end,
            text=segment.text,
            words=[dict(word) for word in segment.words],
        )
        for segment in segments
    ]


def copy_diarization(turns: list[DiarizationSegment]) -> list[DiarizationSegment]:
    return [
        DiarizationSegment(start=turn.start, end=turn.end, speaker=turn.speaker)
        for turn in turns
    ]


def aligned_segments_from_result(result: TranscriptResult) -> list[RawSegment]:
    segments: list[RawSegment] = []
    for block in result.segments:
        words = [
            {"word": word.word, "start": word.start, "end": word.end}
            for word in block.words
        ]
        segments.append(
            RawSegment(
                start=block.start,
                end=block.end,
                text=block.text,
                words=words,
            )
        )
    return segments


def raw_segments_from_result(result: TranscriptResult) -> list[RawSegment]:
    if result.raw_segments:
        return copy_raw_segments(result.raw_segments)
    return aligned_segments_from_result(result)


def diarization_from_result(result: TranscriptResult) -> list[DiarizationSegment]:
    if result.diarization:
        return copy_diarization(result.diarization)
    turns: list[DiarizationSegment] = []
    for block in result.segments:
        words = block.words or []
        if words:
            labeled = [
                (word.start, word.end, word.speaker or block.speaker)
                for word in words
            ]
        elif block.text:
            labeled = [(block.start, block.end, block.speaker)]
        else:
            continue
        for start, end, speaker in labeled:
            if not speaker or speaker == "UNKNOWN":
                continue
            if turns and turns[-1].speaker == speaker and start <= turns[-1].end + 0.3:
                turns[-1] = DiarizationSegment(
                    turns[-1].start,
                    max(turns[-1].end, end),
                    speaker,
                )
            else:
                turns.append(DiarizationSegment(start, end, speaker))
    return turns
