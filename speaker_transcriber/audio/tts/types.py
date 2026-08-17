from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

VoiceGender = Literal["male", "female", "neutral"]


@dataclass(frozen=True)
class SystemVoice:
    id: str
    name: str
    gender: VoiceGender


@dataclass(frozen=True)
class RenderedSegment:
    index: int
    speaker: str
    wav_path: Path
    duration_seconds: float
    start: float
