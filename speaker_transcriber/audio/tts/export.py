from __future__ import annotations

import threading
from pathlib import Path

from speaker_transcriber.audio.ffmpeg import concat_wav_files, encode_wav_to_mp3
from speaker_transcriber.audio.tts.types import RenderedSegment
from speaker_transcriber.errors import TtsError


def export_rendered_mp3(
    segments: list[RenderedSegment],
    destination: Path,
    cancel_event: threading.Event,
) -> None:
    if not segments:
        raise TtsError("There is no prepared audio to export.")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    combined = destination.with_name(destination.stem + "_concat.wav")
    try:
        concat_wav_files([segment.wav_path for segment in segments], combined, cancel_event)
        encode_wav_to_mp3(combined, destination, cancel_event)
    finally:
        combined.unlink(missing_ok=True)
