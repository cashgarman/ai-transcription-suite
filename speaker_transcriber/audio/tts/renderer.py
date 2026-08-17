from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from pathlib import Path

from speaker_transcriber.audio.tts.backend import TtsBackend
from speaker_transcriber.audio.tts.types import RenderedSegment, SystemVoice
from speaker_transcriber.audio.tts.voices import assign_voices, speakers_in_appearance_order
from speaker_transcriber.audio.tts.wavutil import wav_duration_seconds, write_silence_wav
from speaker_transcriber.errors import ProcessingCancelled, TtsError
from speaker_transcriber.pipeline.types import TranscriptResult
ProgressCallback = Callable[[int, int, str], None]


def normalize_speech_text(text: str) -> str:
    return " ".join((text or "").split())


def cache_fingerprint(
    result: TranscriptResult,
    voice_map: dict[str, SystemVoice],
    *,
    engine: str = "windows",
) -> str:
    hasher = hashlib.sha256()
    hasher.update(engine.encode("utf-8"))
    hasher.update(b"\n")
    for speaker, voice in sorted(voice_map.items()):
        hasher.update(speaker.encode("utf-8"))
        hasher.update(b"=")
        hasher.update(voice.id.encode("utf-8"))
        hasher.update(b";")
    hasher.update(b"\n")
    for segment in result.segments:
        hasher.update(segment.speaker.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(normalize_speech_text(segment.text).encode("utf-8"))
        hasher.update(b"\n")
    return hasher.hexdigest()[:24]


def _manifest_path(work_dir: Path) -> Path:
    return work_dir / "manifest.json"


def load_cached_render(work_dir: Path) -> list[RenderedSegment] | None:
    manifest_file = _manifest_path(work_dir)
    if not manifest_file.is_file():
        return None
    try:
        payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    rendered: list[RenderedSegment] = []
    for item in payload.get("segments") or []:
        wav_path = work_dir / str(item["wav"])
        if not wav_path.is_file():
            return None
        rendered.append(
            RenderedSegment(
                index=int(item["index"]),
                speaker=str(item["speaker"]),
                wav_path=wav_path,
                duration_seconds=float(item["duration_seconds"]),
                start=float(item["start"]),
            )
        )
    return rendered


def _save_manifest(work_dir: Path, segments: list[RenderedSegment]) -> None:
    payload = {
        "segments": [
            {
                "index": segment.index,
                "speaker": segment.speaker,
                "wav": segment.wav_path.name,
                "duration_seconds": segment.duration_seconds,
                "start": segment.start,
            }
            for segment in segments
        ]
    }
    _manifest_path(work_dir).write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def render_transcript(
    result: TranscriptResult,
    *,
    backend: TtsBackend,
    work_dir: Path,
    progress_cb: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    voice_map: dict[str, SystemVoice] | None = None,
) -> list[RenderedSegment]:
    cancel = cancel_event or threading.Event()
    segments = [segment for segment in result.segments]
    if not segments:
        raise TtsError("There is no transcript dialogue to speak.")

    if voice_map is None:
        voices = backend.list_voices()
        voice_map = assign_voices(
            speakers_in_appearance_order(result),
            voices,
            genders=result.speaker_genders,
        )

    work_dir.mkdir(parents=True, exist_ok=True)
    cached = load_cached_render(work_dir)
    if cached is not None and len(cached) == len(segments):
        if progress_cb:
            progress_cb(len(cached), len(cached), "Using cached audio")
        return cached

    rendered: list[RenderedSegment] = []
    total = len(segments)
    for index, segment in enumerate(segments):
        if cancel.is_set():
            raise ProcessingCancelled()
        voice = voice_map.get(segment.speaker)
        if voice is None:
            raise TtsError(f"No voice was assigned to speaker {segment.speaker}.")
        if progress_cb:
            progress_cb(index, total, f"Rendering segment {index + 1} of {total}…")
        wav_path = work_dir / f"{index:04d}.wav"
        text = normalize_speech_text(segment.text)
        if text:
            backend.synthesize(text, voice.id, wav_path)
        else:
            write_silence_wav(wav_path)
        rendered.append(
            RenderedSegment(
                index=index,
                speaker=segment.speaker,
                wav_path=wav_path,
                duration_seconds=wav_duration_seconds(wav_path),
                start=segment.start,
            )
        )
    if progress_cb:
        progress_cb(total, total, "Audio is ready")
    _save_manifest(work_dir, rendered)
    return rendered
