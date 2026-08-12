from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from speaker_transcriber.audio.sources import MediaSource
from speaker_transcriber.config import app_data_dir
from speaker_transcriber.export.json_exporter import from_json_dict, to_json_dict
from speaker_transcriber.pipeline.types import TranscriptResult


LOGGER = logging.getLogger("speaker_transcriber.cache")


class TranscriptCache:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or (app_data_dir() / "transcripts")

    def _cache_stem(self, source: Path | list[Path]) -> str:
        if isinstance(source, Path):
            return MediaSource.parse(source).cache_key()
        return MediaSource.parse(source).cache_key()

    def path_for(self, source: Path | list[Path]) -> Path:
        return self.directory / f"{self._cache_stem(source)}.json"

    def exists(self, source: Path | list[Path]) -> bool:
        return self.path_for(source).is_file()

    def load(self, source: Path | list[Path]) -> TranscriptResult | None:
        path = self.path_for(source)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            result = from_json_dict(data)
            media_source = MediaSource.parse(source)
            result.source_file = media_source.source_file_for_result()
            result.source_files = media_source.source_files_for_result()
            return result
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            LOGGER.warning("Failed to load transcript cache %s: %s", path, exc)
            return None

    def save(self, result: TranscriptResult) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        if result.source_files:
            cache_source: Path | list[Path] = [
                Path(path) for path in result.source_files
            ]
        else:
            cache_source = Path(result.source_file)
        path = self.path_for(cache_source)
        payload = json.dumps(to_json_dict(result), indent=2, ensure_ascii=False) + "\n"
        directory = path.parent
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            delete=False,
            suffix=".tmp",
        ) as handle:
            handle.write(payload)
            temp_path = handle.name
        os.replace(temp_path, path)

    def delete(self, source: Path | list[Path]) -> None:
        path = self.path_for(source)
        if path.is_file():
            path.unlink()
