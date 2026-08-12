from __future__ import annotations

from speaker_transcriber.pipeline.types import TranscriptResult


SPEAKER_COLORS = (
    "#4FC3F7",
    "#FFB74D",
    "#81C784",
    "#BA68C8",
    "#E57373",
    "#4DB6AC",
    "#FFD54F",
    "#90A4AE",
)


def speaker_color_map(result: TranscriptResult) -> dict[str, str]:
    speaker_order = sorted(result.speakers)
    return {
        speaker: SPEAKER_COLORS[index % len(SPEAKER_COLORS)]
        for index, speaker in enumerate(speaker_order)
    }


def display_speaker(result: TranscriptResult, speaker: str) -> str:
    return result.speakers.get(speaker, speaker)


def speaker_speaking_seconds(result: TranscriptResult) -> dict[str, float]:
    totals: dict[str, float] = {}
    for segment in result.segments:
        duration = max(segment.end - segment.start, 0.0)
        totals[segment.speaker] = totals.get(segment.speaker, 0.0) + duration
    return totals


def format_speaking_duration(seconds: float) -> str:
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, remainder = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {remainder}s ({seconds:.1f} s)"
    return f"{minutes}m {remainder}s ({seconds:.1f} s)"


def clock_timestamp(seconds: float, milliseconds: bool = False) -> str:
    total_milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    if milliseconds:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def subtitle_timestamp(seconds: float, separator: str = ",") -> str:
    return clock_timestamp(seconds, milliseconds=True).replace(".", separator)
