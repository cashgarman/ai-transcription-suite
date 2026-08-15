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
    *,
    max_duration_seconds: float | None = None,
) -> Iterator[tuple[Path, MediaInfo]]:
    paths = coerce_source_paths(sources)
    if not paths:
        raise MediaError("No media files were provided.")
    media_info = probe_media_sources(paths)
    effective_duration = media_info.duration_seconds
    if max_duration_seconds is not None and max_duration_seconds > 0:
        effective_duration = min(effective_duration, max_duration_seconds)
    temporary_directory = tempfile.TemporaryDirectory(prefix="speaker_transcriber_")
    temp_dir = Path(temporary_directory.name)
    audio_path = temp_dir / "audio.wav"
    try:
        if len(paths) == 1:
            extract_audio(
                paths[0],
                audio_path,
                effective_duration,
                cancel_event,
                on_progress,
                max_duration_seconds=max_duration_seconds,
            )
        else:
            chunks: list[Path] = []
            completed_duration = 0.0
            for index, source in enumerate(paths):
                chunk_info = probe_media(source)
                chunk_path = temp_dir / f"chunk_{index:03d}.wav"
                chunk_cap = None
                if max_duration_seconds is not None:
                    remaining = max(0.0, max_duration_seconds - completed_duration)
                    if remaining <= 0:
                        break
                    chunk_cap = min(chunk_info.duration_seconds, remaining)

                def chunk_progress(
                    value: float,
                    *,
                    chunk_duration: float = (
                        chunk_cap if chunk_cap is not None else chunk_info.duration_seconds
                    ),
                    completed: float = completed_duration,
                ) -> None:
                    if on_progress is None:
                        return
                    processed = completed + value * chunk_duration
                    on_progress(min(processed / effective_duration, 1.0))

                extract_audio(
                    source,
                    chunk_path,
                    chunk_cap if chunk_cap is not None else chunk_info.duration_seconds,
                    cancel_event,
                    chunk_progress,
                    max_duration_seconds=chunk_cap,
                )
                completed_duration += (
                    chunk_cap if chunk_cap is not None else chunk_info.duration_seconds
                )
                chunks.append(chunk_path)
                if (
                    max_duration_seconds is not None
                    and completed_duration >= max_duration_seconds
                ):
                    break
            if on_progress:
                on_progress(min(completed_duration / effective_duration, 0.99))
            concat_wav_files(chunks, audio_path, cancel_event)
            if on_progress:
                on_progress(1.0)
        yield audio_path, MediaInfo(
            duration_seconds=effective_duration,
            has_audio=True,
        )
    finally:
        temporary_directory.cleanup()
