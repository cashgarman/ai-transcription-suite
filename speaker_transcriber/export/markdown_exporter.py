from __future__ import annotations

from pathlib import Path

from speaker_transcriber.export.common import clock_timestamp, display_speaker
from speaker_transcriber.pipeline.types import TranscriptResult


def render_markdown(result: TranscriptResult) -> str:
    lines = [f"# Transcript: {result.source_name}", ""]
    for segment in result.segments:
        lines.extend(
            [
                f"## {display_speaker(result, segment.speaker)}",
                "",
                f"*{clock_timestamp(segment.start)} – {clock_timestamp(segment.end)}*",
                "",
                segment.text,
                "",
            ]
        )
        if segment.overlapping_speakers:
            lines.extend(
                [
                    f"> Overlapping speech: {', '.join(segment.overlapping_speakers)}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def export_markdown(result: TranscriptResult, path: Path) -> None:
    path.write_text(render_markdown(result), encoding="utf-8")
