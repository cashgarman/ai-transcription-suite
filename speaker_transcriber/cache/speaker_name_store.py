from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from speaker_transcriber.audio.sources import MediaSource
from speaker_transcriber.config import app_data_dir
from speaker_transcriber.speaker_names import (
    custom_speaker_names,
    merge_cached_speaker_names,
)


LOGGER = logging.getLogger("speaker_transcriber.cache")


class SpeakerNameStore:
    """Persists display names alongside transcript cache files."""

    def __init__(self, directory: Path | None = None) -> None:
        # Keep names next to transcript JSON caches under transcripts/.
        self.directory = directory or (app_data_dir() / "transcripts")
        self._legacy_path = app_data_dir() / "speaker_names" / "sessions.json"

    def path_for(self, sources: Path | list[Path]) -> Path:
        return self.directory / f"{MediaSource.parse(sources).cache_key()}.speakers.json"

    def load(self, sources: Path | list[Path]) -> dict[str, str]:
        path = self.path_for(sources)
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                LOGGER.warning("Failed to load speaker names %s: %s", path, exc)
                return {}
            return self._normalize_names(payload)

        return self._load_legacy(sources)

    def save(self, sources: Path | list[Path], names: dict[str, str]) -> None:
        cleaned = merge_cached_speaker_names(names, self.load(sources))
        path = self.path_for(sources)
        self.directory.mkdir(parents=True, exist_ok=True)
        if not cleaned:
            if path.is_file():
                path.unlink()
            return
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

    def apply_to_names(
        self,
        sources: Path | list[Path],
        speakers: dict[str, str],
    ) -> dict[str, str]:
        stored = self.load(sources)
        if not stored:
            return dict(speakers)
        merged = dict(speakers)
        for label, name in stored.items():
            if label in merged:
                merged[label] = name
        return merged

    @staticmethod
    def _normalize_names(names: object) -> dict[str, str]:
        if not isinstance(names, dict):
            return {}
        return {
            str(label): str(name).strip()
            for label, name in custom_speaker_names(
                {str(key): str(value) for key, value in names.items()}
            ).items()
        }

    def _load_legacy(self, sources: Path | list[Path]) -> dict[str, str]:
        if not self._legacy_path.is_file():
            return {}
        try:
            payload = json.loads(self._legacy_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            LOGGER.warning(
                "Failed to load legacy speaker name store %s: %s",
                self._legacy_path,
                exc,
            )
            return {}
        if not isinstance(payload, dict):
            return {}
        sessions = payload.get("sessions", {})
        if not isinstance(sessions, dict):
            return {}

        media_source = MediaSource.parse(sources)
        cache_key = media_source.cache_key()
        if cache_key in sessions:
            return self._normalize_names(sessions.get(cache_key))

        # Older builds keyed single/multi sources with an mtime digest.
        for key, names in sessions.items():
            if not isinstance(key, str):
                continue
            if key == cache_key or key.startswith(f"{media_source.primary_path.stem}_"):
                normalized = self._normalize_names(names)
                if normalized:
                    return normalized
        return {}
