from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from speaker_transcriber.audio.ffmpeg import is_supported_media
from speaker_transcriber.errors import MediaError


@dataclass(frozen=True)
class MediaSource:
    paths: tuple[Path, ...]

    @classmethod
    def parse(
        cls,
        value: str | Path | list[str | Path] | tuple[str | Path, ...],
    ) -> MediaSource:
        if isinstance(value, (list, tuple)):
            raw_paths = [Path(item) for item in value]
        else:
            raw_paths = [Path(value)]
        if not raw_paths:
            raise MediaError("No media files were provided.")
        return cls(paths=tuple(path.resolve() for path in raw_paths))

    @property
    def is_multi(self) -> bool:
        return len(self.paths) > 1

    @property
    def primary_path(self) -> Path:
        return self.paths[0]

    def validate(self) -> None:
        for path in self.paths:
            if not path.is_file():
                raise MediaError(f"Media file not found: {path}")
            if not is_supported_media(path):
                raise MediaError(
                    f"Unsupported media format: {path.suffix or '(none)'} ({path.name})"
                )

    def source_file_for_result(self) -> str:
        return str(self.primary_path)

    def source_files_for_result(self) -> list[str]:
        return [str(path) for path in self.paths]

    def cache_key(self) -> str:
        if not self.is_multi:
            return self.primary_path.stem
        payload = [
            {
                "path": str(path),
                "mtime": path.stat().st_mtime,
                "size": path.stat().st_size,
            }
            for path in self.paths
        ]
        digest = hashlib.sha256(json.dumps(payload).encode()).hexdigest()[:16]
        return f"{self.primary_path.stem}_{digest}"

    def summary_label(self) -> str:
        if not self.is_multi:
            return self.primary_path.name
        return f"{self.primary_path.name} (+ {len(self.paths) - 1} more)"


def coerce_source_paths(
    value: str | Path | list[str | Path] | tuple[str | Path, ...],
) -> list[Path]:
    return list(MediaSource.parse(value).paths)
