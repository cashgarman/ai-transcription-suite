from __future__ import annotations

import sys

from speaker_transcriber.audio.tts.backend import TtsBackend, WindowsTtsBackend
from speaker_transcriber.audio.tts.piper_backend import PiperTtsBackend
from speaker_transcriber.errors import TtsError
from speaker_transcriber.models.tts_catalog import (
    DEFAULT_TTS_MODEL,
    WINDOWS_TTS_MODEL,
    is_piper_voice_id,
)


def create_tts_backend(
    model_id: str,
    *,
    extra_voice_ids: list[str] | None = None,
) -> TtsBackend:
    selected = (model_id or DEFAULT_TTS_MODEL).strip() or DEFAULT_TTS_MODEL
    if selected == WINDOWS_TTS_MODEL:
        if sys.platform != "win32":
            raise TtsError("Windows voices are only available on Windows.")
        return WindowsTtsBackend()
    if is_piper_voice_id(selected):
        return PiperTtsBackend(extra_voice_ids=extra_voice_ids)
    if sys.platform == "win32":
        return WindowsTtsBackend()
    raise TtsError(f"Unknown text-to-speech model: {selected}")
