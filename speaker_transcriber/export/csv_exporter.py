from __future__ import annotations

import csv
import io
from pathlib import Path

from speaker_transcriber.export.common import display_speaker
from speaker_transcriber.pipeline.types import TranscriptResult


def render_csv(result: TranscriptResult) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["start", "end", "speaker", "text"])
    for segment in result.segments:
        writer.writerow(
            [
                f"{segment.start:.3f}",
                f"{segment.end:.3f}",
                display_speaker(result, segment.speaker),
                segment.text,
            ]
        )
    return output.getvalue()


def export_csv(result: TranscriptResult, path: Path) -> None:
    path.write_text(render_csv(result), encoding="utf-8", newline="")
