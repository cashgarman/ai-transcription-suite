from __future__ import annotations

import json
from pathlib import Path

from speaker_transcriber.pipeline.types import (
    DiarizationSegment,
    RawSegment,
    TranscriptResult,
    TranscriptSegment,
    Word,
)


def to_json_dict(result: TranscriptResult, *, include_pipeline_cache: bool = False) -> dict:
    segments = []
    for segment in result.segments:
        item = {
            "start": segment.start,
            "end": segment.end,
            "speaker": segment.speaker,
            "text": segment.text,
            "words": [],
        }
        if segment.overlapping_speakers:
            item["overlapping_speakers"] = segment.overlapping_speakers
        if segment.uncertain:
            item["uncertain"] = True
        for word in segment.words:
            word_item = {
                "word": word.word,
                "start": word.start,
                "end": word.end,
                "speaker": word.speaker,
            }
            if word.overlapping_speakers:
                word_item["overlapping_speakers"] = word.overlapping_speakers
            if word.uncertain:
                word_item["uncertain"] = True
            item["words"].append(word_item)
        segments.append(item)
    payload = {
        "source_file": result.source_file,
        "language": result.language,
        "duration_seconds": result.duration_seconds,
        "speakers": result.speakers,
        "metadata": {
            "speaker_display_names": dict(result.speakers),
        },
        "segments": segments,
        "alignment_available": result.alignment_available,
        "diarization_available": result.diarization_available,
    }
    if result.source_files:
        payload["source_files"] = list(result.source_files)
    if result.fallback_config:
        payload["fallback_config"] = result.fallback_config
    if include_pipeline_cache:
        if result.raw_segments:
            payload["raw_segments"] = [
                {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                    "words": [dict(word) for word in segment.words],
                }
                for segment in result.raw_segments
            ]
        if result.diarization:
            payload["diarization"] = [
                {
                    "start": turn.start,
                    "end": turn.end,
                    "speaker": turn.speaker,
                }
                for turn in result.diarization
            ]
    return payload


def from_json_dict(data: dict) -> TranscriptResult:
    segments: list[TranscriptSegment] = []
    for item in data.get("segments", []):
        words: list[Word] = []
        for word_item in item.get("words", []):
            words.append(
                Word(
                    word=str(word_item["word"]),
                    start=float(word_item["start"]),
                    end=float(word_item["end"]),
                    speaker=str(word_item.get("speaker", "UNKNOWN")),
                    overlapping_speakers=list(
                        word_item.get("overlapping_speakers", [])
                    ),
                    uncertain=bool(word_item.get("uncertain", False)),
                )
            )
        segments.append(
            TranscriptSegment(
                start=float(item["start"]),
                end=float(item["end"]),
                speaker=str(item["speaker"]),
                text=str(item["text"]),
                words=words,
                overlapping_speakers=list(item.get("overlapping_speakers", [])),
                uncertain=bool(item.get("uncertain", False)),
            )
        )
    speakers = {str(key): str(value) for key, value in data.get("speakers", {}).items()}
    metadata = data.get("metadata", {})
    metadata_names = metadata.get("speaker_display_names", {})
    if metadata_names:
        speakers.update(
            {str(key): str(value) for key, value in metadata_names.items()}
        )
    return TranscriptResult(
        source_file=str(data["source_file"]),
        language=str(data.get("language", "unknown")),
        duration_seconds=float(data.get("duration_seconds", 0.0)),
        speakers=speakers,
        segments=segments,
        alignment_available=bool(data.get("alignment_available", False)),
        diarization_available=bool(data.get("diarization_available", False)),
        fallback_config=dict(data.get("fallback_config", {})),
        source_files=[str(path) for path in data.get("source_files", [])],
        raw_segments=_raw_segments_from_payload(data.get("raw_segments")),
        diarization=_diarization_from_payload(data.get("diarization")),
    )


def _raw_segments_from_payload(payload: object) -> list[RawSegment]:
    if not isinstance(payload, list):
        return []
    segments: list[RawSegment] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        words = item.get("words") if isinstance(item.get("words"), list) else []
        segments.append(
            RawSegment(
                start=float(item.get("start", 0.0)),
                end=float(item.get("end", 0.0)),
                text=str(item.get("text", "")),
                words=[dict(word) for word in words if isinstance(word, dict)],
            )
        )
    return segments


def _diarization_from_payload(payload: object) -> list[DiarizationSegment]:
    if not isinstance(payload, list):
        return []
    turns: list[DiarizationSegment] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        turns.append(
            DiarizationSegment(
                start=float(item.get("start", 0.0)),
                end=float(item.get("end", 0.0)),
                speaker=str(item.get("speaker", "UNKNOWN")),
            )
        )
    return turns


def render_json(result: TranscriptResult) -> str:
    return json.dumps(to_json_dict(result), indent=2, ensure_ascii=False) + "\n"


def export_json(result: TranscriptResult, path: Path) -> None:
    path.write_text(render_json(result), encoding="utf-8")
