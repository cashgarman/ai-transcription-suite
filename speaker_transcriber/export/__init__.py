from __future__ import annotations

from pathlib import Path
from typing import Callable

from speaker_transcriber.export.csv_exporter import export_csv
from speaker_transcriber.export.json_exporter import export_json
from speaker_transcriber.export.markdown_exporter import export_markdown
from speaker_transcriber.export.subtitle_exporter import export_srt, export_vtt
from speaker_transcriber.export.text_exporter import export_text
from speaker_transcriber.pipeline.types import TranscriptResult


EXPORTERS: dict[str, tuple[str, Callable[[TranscriptResult, Path], None]]] = {
    "txt": (".txt", export_text),
    "md": (".md", export_markdown),
    "json": (".json", export_json),
    "srt": (".srt", export_srt),
    "vtt": (".vtt", export_vtt),
    "csv": (".csv", export_csv),
}


def export_result(
    result: TranscriptResult,
    output_directory: str | Path,
    formats: list[str],
) -> list[Path]:
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    base_name = Path(
        result.source_files[0] if result.source_files else result.source_file
    ).stem
    created = []
    for format_name in formats:
        normalized = format_name.lower().lstrip(".")
        if normalized not in EXPORTERS:
            raise ValueError(f"Unsupported export format: {format_name}")
        extension, exporter = EXPORTERS[normalized]
        destination = directory / f"{base_name}{extension}"
        try:
            exporter(result, destination)
        except OSError as exc:
            raise OSError(f"Could not export {normalized} to {destination}: {exc}") from exc
        created.append(destination)
    return created
