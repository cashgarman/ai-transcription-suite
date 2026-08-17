from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RawSegment:
    start: float
    end: float
    text: str
    words: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DiarizationSegment:
    start: float
    end: float
    speaker: str


@dataclass
class Word:
    word: str
    start: float
    end: float
    speaker: str = "UNKNOWN"
    overlapping_speakers: list[str] = field(default_factory=list)
    uncertain: bool = False


@dataclass
class TranscriptSegment:
    start: float
    end: float
    speaker: str
    text: str
    words: list[Word] = field(default_factory=list)
    overlapping_speakers: list[str] = field(default_factory=list)
    uncertain: bool = False


@dataclass
class TranscriptResult:
    source_file: str
    language: str
    duration_seconds: float
    speakers: dict[str, str] = field(default_factory=dict)
    speaker_genders: dict[str, str] = field(default_factory=dict)
    segments: list[TranscriptSegment] = field(default_factory=list)
    alignment_available: bool = False
    diarization_available: bool = False
    fallback_config: dict[str, Any] = field(default_factory=dict)
    source_files: list[str] = field(default_factory=list)
    raw_segments: list[RawSegment] = field(default_factory=list)
    diarization: list[DiarizationSegment] = field(default_factory=list)

    @property
    def source_name(self) -> str:
        if self.source_files and len(self.source_files) > 1:
            primary = Path(self.source_files[0]).name
            return f"{primary} (+ {len(self.source_files) - 1} more)"
        return Path(self.source_file).name

    def remove_speaker(self, speaker_id: str) -> None:
        self.segments = [
            segment for segment in self.segments if segment.speaker != speaker_id
        ]
        for segment in self.segments:
            segment.overlapping_speakers = [
                speaker
                for speaker in segment.overlapping_speakers
                if speaker != speaker_id
            ]
            for word in segment.words:
                if word.speaker == speaker_id:
                    word.speaker = "UNKNOWN"
                word.overlapping_speakers = [
                    speaker
                    for speaker in word.overlapping_speakers
                    if speaker != speaker_id
                ]
        self.speakers.pop(speaker_id, None)
        self.speaker_genders.pop(speaker_id, None)


@dataclass
class ProgressUpdate:
    stage: str
    progress: float
    message: str
    elapsed_seconds: float
    vram_used_mb: int = 0
    vram_total_mb: int = 0
    stage_fraction: float = 0.0


@dataclass
class ProcessingOptions:
    model: str = "distil-large-v3"
    device: str = "cuda"
    compute_type: str = "int8_float16"
    batch_size: int = 4
    language: str = "auto"
    num_speakers: int | None = None
    min_speakers: int | None = None
    max_speakers: int | None = None
    alignment_device: str = "cuda"
    diarization_device: str = "cuda"
    alignment_model: str = "auto"
    diarization_model: str = "pyannote/speaker-diarization-3.1"
    merge_gap_seconds: float = 0.5
    max_block_duration_seconds: float = 30.0
    inherit_speaker_threshold_seconds: float = 0.3
    hf_token: str | None = field(default=None, repr=False)
    max_input_duration_seconds: float | None = None
    source_duration_seconds: float | None = None
    skip_transcription: bool = False
    skip_alignment: bool = False
    skip_diarization: bool = False
    reuse_raw_segments: list[RawSegment] = field(default_factory=list, repr=False)
    reuse_aligned_segments: list[RawSegment] = field(default_factory=list, repr=False)
    reuse_diarization: list[DiarizationSegment] = field(default_factory=list, repr=False)
