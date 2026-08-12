from speaker_transcriber.export.common import format_speaking_duration, speaker_speaking_seconds
from speaker_transcriber.pipeline.types import TranscriptResult, TranscriptSegment


def _result_with_segments(*segments: TranscriptSegment) -> TranscriptResult:
    speakers = {segment.speaker: segment.speaker for segment in segments}
    return TranscriptResult(
        source_file="meeting.mp4",
        language="en",
        duration_seconds=max((segment.end for segment in segments), default=0.0),
        speakers=speakers,
        segments=list(segments),
    )


def test_speaker_speaking_seconds_sums_segment_durations() -> None:
    result = _result_with_segments(
        TranscriptSegment(0.0, 10.0, "SPEAKER_00", "Hello"),
        TranscriptSegment(10.0, 25.5, "SPEAKER_01", "Hi"),
        TranscriptSegment(30.0, 40.0, "SPEAKER_00", "Again"),
    )
    totals = speaker_speaking_seconds(result)
    assert totals["SPEAKER_00"] == 20.0
    assert totals["SPEAKER_01"] == 15.5


def test_format_speaking_duration() -> None:
    assert format_speaking_duration(12.4) == "12.4 s"
    assert format_speaking_duration(95.0) == "1m 35s (95.0 s)"
