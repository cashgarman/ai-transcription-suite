from __future__ import annotations

from pathlib import Path

from speaker_transcriber.export.common import clock_timestamp, display_speaker, render_speaker_legend
from speaker_transcriber.pipeline.types import TranscriptResult


def render_text(result: TranscriptResult) -> str:
    blocks = []
    for segment in result.segments:
        overlap = (
            f" [overlap: {', '.join(display_speaker(result, speaker) for speaker in segment.overlapping_speakers)}]"
            if segment.overlapping_speakers
            else ""
        )
        blocks.append(
            f"[{clock_timestamp(segment.start)} - {clock_timestamp(segment.end)}] "
            f"{display_speaker(result, segment.speaker)}{overlap}\n{segment.text}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def render_summary_source(result: TranscriptResult) -> str:
    legend = render_speaker_legend(result)
    body = render_text(result)
    if legend:
        return f"{legend}\n\n{body}"
    return body


def export_text(result: TranscriptResult, path: Path) -> None:
    path.write_text(render_text(result), encoding="utf-8")
