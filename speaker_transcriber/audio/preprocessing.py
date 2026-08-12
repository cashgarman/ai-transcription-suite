from __future__ import annotations

import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from speaker_transcriber.audio.ffmpeg import (
    MediaInfo,
    concat_wav_files,
    extract_audio,
    probe_media,
    probe_media_sources,
)
from speaker_transcriber.audio.sources import coerce_source_paths
from speaker_transcriber.errors import MediaError


@contextmanager
def normalized_audio(
    source: str | Path,
    cancel_event: threading.Event,
    on_progress: Callable[[float], None] | None = None,
) -> Iterator[tuple[Path, MediaInfo]]:
    with normalized_media(source, cancel_event, on_progress) as result:
        yield result


@contextmanager
def normalized_media(
    sources: str | Path | list[str | Path] | tuple[str | Path, ...],
    cancel_event: threading.Event,
    on_progress: Callable[[float], None] | None = None,
) -> Iterator[tuple[Path, MediaInfo]]:
    paths = coerce_source_paths(sources)
    if not paths:
        raise MediaError("No media files were provided.")
    media_info = probe_media_sources(paths)
    temporary_directory = tempfile.TemporaryDirectory(prefix="speaker_transcriber_")
    temp_dir = Path(temporary_directory.name)
    audio_path = temp_dir / "audio.wav"
    try:
        if len(paths) == 1:
            extract_audio(
                paths[0],
                audio_path,
                media_info.duration_seconds,
                cancel_event,
                on_progress,
            )
        else:
            chunks: list[Path] = []
            completed_duration = 0.0
            for index, source in enumerate(paths):
                chunk_info = probe_media(source)
                chunk_path = temp_dir / f"chunk_{index:03d}.wav"

                def chunk_progress(
                    value: float,
                    *,
                    chunk_duration: float = chunk_info.duration_seconds,
                    completed: float = completed_duration,
                ) -> None:
                    if on_progress is None:
                        return
                    processed = completed + value * chunk_duration
                    on_progress(min(processed / media_info.duration_seconds, 1.0))

                extract_audio(
                    source,
                    chunk_path,
                    chunk_info.duration_seconds,
                    cancel_event,
                    chunk_progress,
                )
                completed_duration += chunk_info.duration_seconds
                chunks.append(chunk_path)
            if on_progress:
                on_progress(min(completed_duration / media_info.duration_seconds, 0.99))
            concat_wav_files(chunks, audio_path, cancel_event)
            if on_progress:
                on_progress(1.0)
        yield audio_path, media_info
    finally:
        temporary_directory.cleanup()
