from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from speaker_transcriber.errors import MediaError, ProcessingCancelled


LOGGER = logging.getLogger("speaker_transcriber.audio")
AUDIO_EXTENSIONS = frozenset(
    {
        ".aac",
        ".flac",
        ".m4a",
        ".mp3",
        ".ogg",
        ".opus",
        ".wav",
    }
)
VIDEO_EXTENSIONS = frozenset(
    {
        ".avi",
        ".mkv",
        ".mov",
        ".mp4",
        ".webm",
    }
)
SUPPORTED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS


def is_supported_media(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS


def format_extensions_for_dialog(extensions: frozenset[str]) -> str:
    return ";".join(f"*{extension}" for extension in sorted(extensions))


def media_file_dialog_filter() -> str:
    all_supported = format_extensions_for_dialog(SUPPORTED_EXTENSIONS)
    audio = format_extensions_for_dialog(AUDIO_EXTENSIONS)
    video = format_extensions_for_dialog(VIDEO_EXTENSIONS)
    return (
        f"All supported media ({all_supported});;"
        f"Audio files ({audio});;"
        f"Video files ({video});;"
        "All files (*.*)"
    )


@dataclass(frozen=True)
class MediaInfo:
    duration_seconds: float
    has_audio: bool


def _require_executable(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise MediaError(
            f"{name} is not installed or is not on PATH. Install FFmpeg and restart the application."
        )
    return executable


def probe_media(path: str | Path) -> MediaInfo:
    source = Path(path)
    if not source.is_file():
        raise MediaError(f"Media file not found: {source}")
    if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise MediaError(f"Unsupported media format: {source.suffix or '(none)'}")
    ffprobe = _require_executable("ffprobe")
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type",
        "-of",
        "json",
        str(source),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "The file may be corrupt."
        raise MediaError(f"FFprobe could not read the media file: {detail}")
    try:
        payload = json.loads(completed.stdout)
        duration = float(payload.get("format", {}).get("duration", 0))
        has_audio = any(
            stream.get("codec_type") == "audio" for stream in payload.get("streams", [])
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MediaError("FFprobe returned invalid media information.") from exc
    if not has_audio:
        raise MediaError("The selected file does not contain an audio stream.")
    if duration <= 0:
        raise MediaError("The selected file has no measurable audio duration.")
    return MediaInfo(duration_seconds=duration, has_audio=True)


def extract_audio(
    source: str | Path,
    destination: str | Path,
    duration_seconds: float,
    cancel_event: threading.Event,
    on_progress: Callable[[float], None] | None = None,
) -> None:
    ffmpeg = _require_executable("ffmpeg")
    command = [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        "-progress",
        "pipe:1",
        "-nostats",
        str(destination),
    ]
    LOGGER.info("Extracting normalized audio from %s", Path(source).name)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stderr_lines: list[str] = []

    def read_stderr() -> None:
        if process.stderr is not None:
            stderr_lines.extend(process.stderr.readlines())

    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stderr_thread.start()
    try:
        if process.stdout is not None:
            while True:
                if cancel_event.is_set():
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise ProcessingCancelled()
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line.startswith("out_time_ms=") and on_progress:
                    try:
                        elapsed = int(line.split("=", 1)[1]) / 1_000_000
                        on_progress(min(elapsed / duration_seconds, 1.0))
                    except (ValueError, ZeroDivisionError):
                        pass
                if not line:
                    time.sleep(0.01)
        return_code = process.wait()
        stderr_thread.join(timeout=1)
        if return_code != 0:
            detail = "".join(stderr_lines).strip()
            raise MediaError(
                "FFmpeg could not decode the media file. "
                + (detail[-1000:] if detail else "The audio may be corrupt.")
            )
        if on_progress:
            on_progress(1.0)
    finally:
        if process.poll() is None:
            process.kill()


def _escape_concat_path(path: Path) -> str:
    normalized = str(path.resolve()).replace("\\", "/")
    escaped = normalized.replace("'", "'\\''")
    return f"file '{escaped}'"


def concat_wav_files(
    sources: list[Path],
    destination: str | Path,
    cancel_event: threading.Event,
) -> None:
    if cancel_event.is_set():
        raise ProcessingCancelled()
    chunk_paths = [Path(source) for source in sources]
    if not chunk_paths:
        raise MediaError("No audio chunks were provided for concatenation.")
    destination_path = Path(destination)
    if len(chunk_paths) == 1:
        destination_path.write_bytes(chunk_paths[0].read_bytes())
        return

    list_path = destination_path.parent / "concat_list.txt"
    list_path.write_text(
        "\n".join(_escape_concat_path(chunk) for chunk in chunk_paths) + "\n",
        encoding="utf-8",
    )
    ffmpeg = _require_executable("ffmpeg")
    command = [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c",
        "copy",
        str(destination_path),
    ]
    LOGGER.info("Concatenating %d audio segments", len(chunk_paths))
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if cancel_event.is_set():
        raise ProcessingCancelled()
    if completed.returncode != 0:
        detail = completed.stderr.strip()
        raise MediaError(
            "FFmpeg could not merge the audio segments. "
            + (detail[-1000:] if detail else "The audio may be corrupt.")
        )


def probe_media_sources(sources: list[Path]) -> MediaInfo:
    if not sources:
        raise MediaError("No media files were provided.")
    total_duration = 0.0
    for source in sources:
        info = probe_media(source)
        total_duration += info.duration_seconds
    return MediaInfo(duration_seconds=total_duration, has_audio=True)
