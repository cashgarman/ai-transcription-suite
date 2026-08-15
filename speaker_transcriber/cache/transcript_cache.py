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
from speaker_transcriber.prompts import DEFAULT_STYLE, normalize_style, style_ids
from speaker_transcriber.speaker_names import (
    apply_cached_speaker_names,
    custom_speaker_names,
    merge_cached_speaker_names,
)


LOGGER = logging.getLogger("speaker_transcriber.cache")


class TranscriptCache:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or (app_data_dir() / "transcripts")
        self._migrated: set[str] = set()

    def _cache_stem(self, source: Path | list[Path]) -> str:
        media_source = MediaSource.parse(source)
        stem = media_source.cache_key()
        self._adopt_legacy_files(media_source, stem)
        return stem

    def _adopt_legacy_files(self, media_source: MediaSource, stem: str) -> None:
        """Rename pre-fingerprint cache files so existing recordings stay cached.

        Older single-file caches were keyed on the filename stem alone, which
        collided across directories. Files are only adopted when the cached
        transcript names the same recording.
        """
        legacy_stem = media_source.legacy_cache_key()
        if legacy_stem is None or legacy_stem == stem or legacy_stem in self._migrated:
            return
        self._migrated.add(legacy_stem)
        legacy_transcript = self.directory / f"{legacy_stem}.json"
        if not legacy_transcript.is_file():
            return
        if (self.directory / f"{stem}.json").exists():
            return
        if not self._legacy_source_matches(legacy_transcript, media_source):
            return
        prefix = f"{legacy_stem}."
        for path in list(self.directory.iterdir()):
            if not path.is_file() or not path.name.startswith(prefix):
                continue
            target = self.directory / f"{stem}.{path.name[len(prefix):]}"
            if target.exists():
                continue
            try:
                path.rename(target)
            except OSError as exc:
                LOGGER.warning("Could not migrate cache file %s: %s", path, exc)

    def _legacy_source_matches(self, path: Path, media_source: MediaSource) -> bool:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False
        if not isinstance(data, dict):
            return False
        recorded = str(data.get("source_file", "")).strip()
        if not recorded:
            return False
        try:
            return Path(recorded).resolve() == media_source.primary_path
        except OSError:
            return False

    def path_for(self, source: Path | list[Path]) -> Path:
        return self.directory / f"{self._cache_stem(source)}.json"

    def speakers_path_for(self, source: Path | list[Path]) -> Path:
        return self.directory / f"{self._cache_stem(source)}.speakers.json"

    def summary_path_for(
        self,
        source: Path | list[Path],
        style: str | None = None,
    ) -> Path:
        stem = self._cache_stem(source)
        return self.directory / f"{stem}.summary.{normalize_style(style)}.md"

    def legacy_summary_path_for(self, source: Path | list[Path]) -> Path:
        """Where summaries lived before styles existed: always meeting notes."""
        return self.directory / f"{self._cache_stem(source)}.summary.md"

    def _summary_paths(
        self,
        source: Path | list[Path],
        style: str | None = None,
    ) -> list[Path]:
        """Every file that could hold this style's summary, newest naming first."""
        paths = [self.summary_path_for(source, style)]
        if normalize_style(style) == DEFAULT_STYLE:
            paths.append(self.legacy_summary_path_for(source))
        return paths

    def exists(self, source: Path | list[Path]) -> bool:
        return self.path_for(source).is_file()

    def summary_exists(
        self,
        source: Path | list[Path],
        style: str | None = None,
    ) -> bool:
        return any(path.is_file() for path in self._summary_paths(source, style))

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
                result.speakers = apply_cached_speaker_names(
                    result.speakers,
                    stored_names,
                )
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
        stored_names = self._load_speaker_names(cache_source)
        result.speakers = apply_cached_speaker_names(result.speakers, stored_names)
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

    def load_summary(
        self,
        source: Path | list[Path],
        style: str | None = None,
    ) -> str | None:
        for path in self._summary_paths(source, style):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                LOGGER.warning("Failed to load summary cache %s: %s", path, exc)
                return None
            if text:
                return text
        return None

    def save_summary(
        self,
        source: Path | list[Path],
        markdown: str,
        style: str | None = None,
    ) -> None:
        paths = self._summary_paths(source, style)
        path = paths[0]
        text = (markdown or "").strip()
        if not text:
            for stale in paths:
                if stale.is_file():
                    stale.unlink()
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = text + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.directory,
            delete=False,
            suffix=".tmp",
        ) as handle:
            handle.write(payload)
            temp_path = handle.name
        os.replace(temp_path, path)
        for superseded in paths[1:]:
            if superseded.is_file():
                superseded.unlink()

    def delete(self, source: Path | list[Path]) -> None:
        path = self.path_for(source)
        if path.is_file():
            path.unlink()
        speakers_path = self.speakers_path_for(source)
        if speakers_path.is_file():
            speakers_path.unlink()
        for summary_path in self.summary_paths(source):
            summary_path.unlink()

    def summary_paths(self, source: Path | list[Path]) -> list[Path]:
        """Every stored summary for this recording, whatever style wrote it."""
        found = [self.legacy_summary_path_for(source)]
        found.extend(
            self.summary_path_for(source, style_id) for style_id in style_ids()
        )
        return [path for path in found if path.is_file()]

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
        return custom_speaker_names(
            {
                str(label): str(name).strip()
                for label, name in payload.items()
                if str(name).strip()
            }
        )

    def _save_speaker_names(
        self,
        source: Path | list[Path],
        speakers: dict[str, str],
    ) -> None:
        path = self.speakers_path_for(source)
        cleaned = merge_cached_speaker_names(
            speakers,
            self._load_speaker_names(source),
        )
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
