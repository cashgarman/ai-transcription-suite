from speaker_transcriber.pipeline.types import TranscriptResult, TranscriptSegment, Word


def _result_with_segments(*segments: TranscriptSegment) -> TranscriptResult:
    speakers = {segment.speaker: segment.speaker for segment in segments}
    return TranscriptResult(
        source_file="meeting.mp4",
        language="en",
        duration_seconds=max((segment.end for segment in segments), default=0.0),
        speakers=speakers,
        segments=list(segments),
    )


def test_remove_speaker_drops_segments_and_cleanup_overlaps() -> None:
    result = _result_with_segments(
        TranscriptSegment(
            0.0,
            5.0,
            "SPEAKER_00",
            "Hello",
            words=[Word("Hello", 0.0, 1.0, "SPEAKER_00")],
        ),
        TranscriptSegment(
            5.0,
            10.0,
            "SPEAKER_01",
            "Hi",
            overlapping_speakers=["SPEAKER_00"],
            words=[
                Word(
                    "Hi",
                    5.0,
                    6.0,
                    "SPEAKER_01",
                    overlapping_speakers=["SPEAKER_00"],
                )
            ],
        ),
        TranscriptSegment(10.0, 15.0, "SPEAKER_00", "Again"),
    )
    result.speakers = {"SPEAKER_00": "Alice", "SPEAKER_01": "Bob"}

    result.remove_speaker("SPEAKER_00")

    assert list(result.speakers) == ["SPEAKER_01"]
    assert len(result.segments) == 1
    assert result.segments[0].speaker == "SPEAKER_01"
    assert result.segments[0].overlapping_speakers == []
    assert result.segments[0].words[0].overlapping_speakers == []
