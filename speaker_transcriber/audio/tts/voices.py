from __future__ import annotations

from speaker_transcriber.audio.tts.types import SystemVoice
from speaker_transcriber.errors import TtsError
from speaker_transcriber.pipeline.types import TranscriptResult


def speakers_in_appearance_order(result: TranscriptResult) -> list[str]:
    seen: list[str] = []
    for segment in result.segments:
        if segment.speaker not in seen:
            seen.append(segment.speaker)
    for speaker_id in result.speakers:
        if speaker_id not in seen:
            seen.append(speaker_id)
    return seen


def _voice_pools(voices: list[SystemVoice]) -> tuple[list[SystemVoice], list[SystemVoice]]:
    males = [voice for voice in voices if voice.gender == "male"]
    females = [voice for voice in voices if voice.gender == "female"]
    others = [voice for voice in voices if voice.gender == "neutral"]
    if not males:
        males = list(others) or list(females)
    if not females:
        females = list(others) or list(males)
    return males, females


def assign_voices(
    speakers: list[str],
    voices: list[SystemVoice],
    *,
    genders: dict[str, str] | None = None,
    preferred_voice: str | None = None,
) -> dict[str, SystemVoice]:
    if not speakers:
        return {}
    if not voices:
        raise TtsError("No text-to-speech voices are available.")

    males, females = _voice_pools(voices)
    preferences = genders or {}
    male_used = 0
    female_used = 0
    voice_by_id = {voice.id: voice for voice in voices}
    preferred_used = False

    assigned: dict[str, SystemVoice] = {}
    for index, speaker in enumerate(speakers):
        preferred_gender = preferences.get(speaker)
        chosen: SystemVoice | None = None
        if (
            not preferred_used
            and preferred_voice
            and preferred_voice in voice_by_id
        ):
            candidate = voice_by_id[preferred_voice]
            if preferred_gender is None or candidate.gender == preferred_gender:
                chosen = candidate
                preferred_used = True
        if chosen is None and preferred_gender == "male":
            pool = males
            chosen = pool[male_used % len(pool)]
            male_used += 1
        elif chosen is None and preferred_gender == "female":
            pool = females
            chosen = pool[female_used % len(pool)]
            female_used += 1
        elif chosen is None:
            pool = males if index % 2 == 0 else females
            chosen = pool[(index // 2) % len(pool)]
        assigned[speaker] = chosen
    return assigned
