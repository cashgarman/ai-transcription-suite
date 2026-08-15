from speaker_transcriber.pipeline.stage_cache import (
    aligned_segments_from_result,
    diarization_from_result,
    raw_segments_from_result,
    stage_model_changed,
)
from speaker_transcriber.pipeline.types import (
    DiarizationSegment,
    RawSegment,
    TranscriptResult,
    TranscriptSegment,
    Word,
)


def _result() -> TranscriptResult:
    return TranscriptResult(
        source_file="meeting.mp4",
        language="en",
        duration_seconds=4.0,
        speakers={"SPEAKER_00": "Ada", "SPEAKER_01": "Bob"},
        segments=[
            TranscriptSegment(
                0.0,
                1.5,
                "SPEAKER_00",
                "Hello there",
                [
                    Word("Hello", 0.0, 0.6, "SPEAKER_00"),
                    Word("there", 0.7, 1.4, "SPEAKER_00"),
                ],
            ),
            TranscriptSegment(
                1.6,
                2.4,
                "SPEAKER_01",
                "Hi",
                [Word("Hi", 1.6, 2.3, "SPEAKER_01")],
            ),
        ],
        fallback_config={
            "alignment_model": "auto",
            "diarization_model": "pyannote/speaker-diarization-3.1",
        },
        raw_segments=[
            RawSegment(
                0.0,
                1.5,
                "Hello there",
                words=[{"word": "Hello", "start": 0.1, "end": 0.5}],
            )
        ],
        diarization=[
            DiarizationSegment(0.0, 1.5, "SPEAKER_00"),
            DiarizationSegment(1.5, 2.5, "SPEAKER_01"),
        ],
    )


def test_stage_model_changed_requires_a_cached_result() -> None:
    assert not stage_model_changed(None, "alignment_model", "auto")


def test_stage_model_changed_when_selection_differs() -> None:
    result = _result()
    assert not stage_model_changed(result, "alignment_model", "auto")
    assert stage_model_changed(
        result,
        "alignment_model",
        "jonatasgrosman/wav2vec2-large-xlsr-53-english",
    )
    assert stage_model_changed(
        result,
        "diarization_model",
        "pyannote/speaker-diarization-community-1",
    )
    assert not stage_model_changed(
        result,
        "diarization_model",
        "pyannote/speaker-diarization-3.1",
    )


def test_stage_model_changed_when_cached_model_was_never_recorded() -> None:
    result = _result()
    result.fallback_config = {"model": "distil-large-v3"}
    assert stage_model_changed(result, "alignment_model", "auto")


def test_raw_segments_prefer_stored_whisper_output() -> None:
    result = _result()
    raw = raw_segments_from_result(result)
    assert len(raw) == 1
    assert raw[0].text == "Hello there"
    assert raw[0].words[0]["start"] == 0.1


def test_aligned_segments_come_from_final_words() -> None:
    aligned = aligned_segments_from_result(_result())
    assert aligned[0].words[0]["start"] == 0.0
    assert aligned[1].text == "Hi"


def test_diarization_prefers_stored_turns() -> None:
    turns = diarization_from_result(_result())
    assert [(turn.start, turn.end, turn.speaker) for turn in turns] == [
        (0.0, 1.5, "SPEAKER_00"),
        (1.5, 2.5, "SPEAKER_01"),
    ]


def test_diarization_is_reconstructed_from_labeled_words() -> None:
    result = _result()
    result.diarization = []
    turns = diarization_from_result(result)
    assert turns[0].speaker == "SPEAKER_00"
    assert turns[0].end == 1.4
    assert turns[1].speaker == "SPEAKER_01"
