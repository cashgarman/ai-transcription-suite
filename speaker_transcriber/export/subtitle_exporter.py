from __future__ import annotations

from pathlib import Path

from speaker_transcriber.export.common import display_speaker, subtitle_timestamp
from speaker_transcriber.pipeline.types import TranscriptResult


def render_srt(result: TranscriptResult) -> str:
    cues = []
    for index, segment in enumerate(result.segments, start=1):
        cues.append(
            "\n".join(
                [
                    str(index),
                    f"{subtitle_timestamp(segment.start)} --> "
                    f"{subtitle_timestamp(segment.end)}",
                    f"{display_speaker(result, segment.speaker)}: {segment.text}",
                ]
            )
        )
    return "\n\n".join(cues) + ("\n" if cues else "")


def render_vtt(result: TranscriptResult) -> str:
    cues = ["WEBVTT", ""]
    for segment in result.segments:
        cues.extend(
            [
                f"{subtitle_timestamp(segment.start, '.')} --> "
                f"{subtitle_timestamp(segment.end, '.')}",
                f"<v {display_speaker(result, segment.speaker)}>{segment.text}",
                "",
            ]
        )
    return "\n".join(cues).rstrip() + "\n"


def export_srt(result: TranscriptResult, path: Path) -> None:
    path.write_text(render_srt(result), encoding="utf-8")


def export_vtt(result: TranscriptResult, path: Path) -> None:
    path.write_text(render_vtt(result), encoding="utf-8")
