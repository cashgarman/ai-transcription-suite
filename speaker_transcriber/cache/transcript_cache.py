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

    def speakers_path_for(self, source: Path | list[Path]) -> Path:
        return self.directory / f"{self._cache_stem(source)}.speakers.json"

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
            stored_names = self._load_speaker_names(source)
            if stored_names:
                for label, name in stored_names.items():
                    if label in result.speakers:
                        result.speakers[label] = name
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
        self._save_speaker_names(cache_source, result.speakers)

    def delete(self, source: Path | list[Path]) -> None:
        path = self.path_for(source)
        if path.is_file():
            path.unlink()
        speakers_path = self.speakers_path_for(source)
        if speakers_path.is_file():
            speakers_path.unlink()

    def _load_speaker_names(self, source: Path | list[Path]) -> dict[str, str]:
        path = self.speakers_path_for(source)
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            LOGGER.warning("Failed to load speaker name cache %s: %s", path, exc)
            return {}
        if not isinstance(payload, dict):
            return {}
        return {
            str(label): str(name).strip()
            for label, name in payload.items()
            if str(name).strip()
        }

    def _save_speaker_names(
        self,
        source: Path | list[Path],
        speakers: dict[str, str],
    ) -> None:
        path = self.speakers_path_for(source)
        cleaned = {
            str(label): str(name).strip()
            for label, name in speakers.items()
            if str(name).strip()
        }
        if not cleaned:
            if path.is_file():
                path.unlink()
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        text = json.dumps(cleaned, indent=2, ensure_ascii=False) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.directory,
            delete=False,
            suffix=".tmp",
        ) as handle:
            handle.write(text)
            temp_path = handle.name
        os.replace(temp_path, path)
