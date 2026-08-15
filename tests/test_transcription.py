from speaker_transcriber.models.transcription import (
    RawSegment,
    _looks_like_hallucinated_transcript,
)


def test_hallucination_detector_flags_repeated_thank_you_every_thirty_seconds() -> None:
    segments = [
        RawSegment(0.0, 0.0, "Thank you."),
        RawSegment(30.0, 30.0, "Thank you."),
        RawSegment(60.0, 60.0, "Thank you."),
        RawSegment(90.0, 90.0, "Thank you."),
    ]
    assert _looks_like_hallucinated_transcript(segments, 600.0)


def test_hallucination_detector_allows_real_transcript() -> None:
    segments = [
        RawSegment(0.0, 4.0, "Let's review the agenda for today's meeting."),
        RawSegment(6.0, 11.0, "First item is the budget update."),
    ]
    assert not _looks_like_hallucinated_transcript(segments, 600.0)
