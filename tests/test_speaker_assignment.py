from speaker_transcriber.pipeline.speaker_assignment import assign_speakers, assign_word
from speaker_transcriber.pipeline.types import DiarizationSegment, RawSegment, Word


def test_midpoint_selects_containing_speaker() -> None:
    word = Word("hello", 1.0, 1.5)
    turns = [
        DiarizationSegment(0.0, 1.1, "SPEAKER_00"),
        DiarizationSegment(1.1, 2.0, "SPEAKER_01"),
    ]
    assert assign_word(word, turns, 0.3).speaker == "SPEAKER_01"


def test_overlap_records_secondary_speaker_and_uncertainty() -> None:
    word = Word("yes", 1.0, 2.0)
    turns = [
        DiarizationSegment(0.5, 2.0, "SPEAKER_00"),
        DiarizationSegment(1.0, 1.8, "SPEAKER_01"),
    ]
    assigned = assign_word(word, turns, 0.3)
    assert assigned.speaker == "SPEAKER_00"
    assert assigned.overlapping_speakers == ["SPEAKER_01"]
    assert assigned.uncertain


def test_word_between_turns_inherits_nearest_speaker() -> None:
    word = Word("well", 1.05, 1.15)
    turns = [
        DiarizationSegment(0.0, 1.0, "SPEAKER_00"),
        DiarizationSegment(1.5, 2.0, "SPEAKER_01"),
    ]
    assert assign_word(word, turns, 0.2).speaker == "SPEAKER_00"


def test_large_gap_remains_unknown() -> None:
    word = Word("noise", 3.0, 3.1)
    turns = [DiarizationSegment(0.0, 1.0, "SPEAKER_00")]
    assert assign_word(word, turns, 0.3).speaker == "UNKNOWN"


def test_words_inside_one_whisper_segment_receive_different_speakers() -> None:
    segments = [
        RawSegment(
            0.0,
            2.0,
            "Hello there",
            words=[
                {"word": "Hello", "start": 0.1, "end": 0.6},
                {"word": "there", "start": 1.2, "end": 1.8},
            ],
        )
    ]
    turns = [
        DiarizationSegment(0.0, 1.0, "SPEAKER_00"),
        DiarizationSegment(1.0, 2.0, "SPEAKER_01"),
    ]
    assigned = assign_speakers(segments, turns)
    assert [word.speaker for word in assigned] == ["SPEAKER_00", "SPEAKER_01"]
