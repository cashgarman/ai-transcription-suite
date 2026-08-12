from __future__ import annotations

import json
import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path

from speaker_transcriber.audio.sources import MediaSource
from speaker_transcriber.config import app_data_dir


LOGGER = logging.getLogger("speaker_transcriber.cache")


def _speaker_session_key(sources: Path | list[Path]) -> str:
    media_source = MediaSource.parse(sources)
    payload = [
        {
            "path": str(path),
            "mtime": path.stat().st_mtime,
            "size": path.stat().st_size,
        }
        for path in sorted(media_source.paths, key=lambda item: str(item))
    ]
    digest = hashlib.sha256(json.dumps(payload).encode()).hexdigest()[:16]
    stem = Path(payload[0]["path"]).stem
    return f"{stem}_{digest}"


class SpeakerNameStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or (app_data_dir() / "speaker_names")
        self.path = self.directory / "sessions.json"

    def _session_key(self, sources: Path | list[Path]) -> str:
        return _speaker_session_key(sources)

    def load(self, sources: Path | list[Path]) -> dict[str, str]:
        session_key = self._session_key(sources)
        payload = self._read_payload()
        names = payload.get("sessions", {}).get(session_key, {})
        return {str(key): str(value) for key, value in names.items()}

    def save(self, sources: Path | list[Path], names: dict[str, str]) -> None:
        cleaned = {
            str(label): str(name).strip()
            for label, name in names.items()
            if str(name).strip()
        }
        session_key = self._session_key(sources)
        payload = self._read_payload()
        sessions = payload.setdefault("sessions", {})
        if cleaned:
            sessions[session_key] = cleaned
        else:
            sessions.pop(session_key, None)
        self._write_payload(payload)

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

    def _read_payload(self) -> dict:
        if not self.path.is_file():
            return {"sessions": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            LOGGER.warning("Failed to load speaker name store %s: %s", self.path, exc)
            return {"sessions": {}}
        if not isinstance(payload, dict):
            return {"sessions": {}}
        payload.setdefault("sessions", {})
        return payload

    def _write_payload(self, payload: dict) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.directory,
            delete=False,
            suffix=".tmp",
        ) as handle:
            handle.write(text)
            temp_path = handle.name
        os.replace(temp_path, self.path)
