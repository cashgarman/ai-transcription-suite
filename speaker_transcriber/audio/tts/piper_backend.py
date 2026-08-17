from __future__ import annotations

import wave
from pathlib import Path

from speaker_transcriber.audio.tts.types import SystemVoice, VoiceGender
from speaker_transcriber.errors import TtsError
from speaker_transcriber.models.tts_catalog import (
    is_piper_voice_installed,
    list_installed_piper_voice_ids,
    piper_voice_files,
    piper_voice_spec,
)


def _parse_gender(raw: str) -> VoiceGender:
    lowered = (raw or "").strip().lower()
    if lowered == "male":
        return "male"
    if lowered == "female":
        return "female"
    return "neutral"


class PiperTtsBackend:
    """Offline Piper ONNX voices downloaded from rhasspy/piper-voices."""

    def __init__(self, extra_voice_ids: list[str] | None = None) -> None:
        self._extra_voice_ids = list(extra_voice_ids or [])
        self._voices: dict[str, object] = {}

    def list_voices(self) -> list[SystemVoice]:
        voices: list[SystemVoice] = []
        for voice_id in list_installed_piper_voice_ids(self._extra_voice_ids):
            spec = piper_voice_spec(voice_id)
            if spec is None:
                continue
            voices.append(
                SystemVoice(
                    id=voice_id,
                    name=spec.display_name,
                    gender=_parse_gender(spec.gender),
                )
            )
        return voices

    def synthesize(self, text: str, voice_id: str, output_wav: Path) -> None:
        if not is_piper_voice_installed(voice_id):
            raise TtsError(
                f"The Piper voice '{voice_id}' is not downloaded yet. "
                "Choose Add Models… to download it."
            )
        onnx_path, config_path = piper_voice_files(voice_id)
        try:
            from piper import PiperVoice
        except ImportError as exc:
            raise TtsError(
                "Piper TTS is not installed. Install the piper-tts package to use "
                "open-source voice models."
            ) from exc
        voice = self._voices.get(voice_id)
        if voice is None:
            voice = PiperVoice.load(str(onnx_path), config_path=str(config_path))
            self._voices[voice_id] = voice
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        try:
            with wave.open(str(output_wav), "wb") as wav_file:
                voice.synthesize_wav(text, wav_file)
        except Exception as exc:
            raise TtsError(f"Piper could not render speech with voice '{voice_id}'.") from exc
        if not output_wav.is_file() or output_wav.stat().st_size == 0:
            raise TtsError(f"Piper did not write an audio file for voice '{voice_id}'.")

    def close(self) -> None:
        self._voices.clear()
