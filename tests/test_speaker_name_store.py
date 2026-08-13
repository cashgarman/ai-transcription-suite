from pathlib import Path

from speaker_transcriber.cache.speaker_name_store import SpeakerNameStore
from speaker_transcriber.cache.transcript_cache import TranscriptCache
from speaker_transcriber.pipeline.types import TranscriptResult, TranscriptSegment, Word


def sample_result(source_file: str = "meeting.mp4") -> TranscriptResult:
    word = Word("Welcome", 2.1, 2.6, "SPEAKER_00")
    segment = TranscriptSegment(
        2.1,
        6.4,
        "SPEAKER_00",
        "Welcome.",
        [word],
    )
    return TranscriptResult(
        source_file=source_file,
        language="en",
        duration_seconds=123.45,
        speakers={"SPEAKER_00": "Alice"},
        segments=[segment],
        alignment_available=True,
        diarization_available=True,
        fallback_config={"model": "distil-large-v3", "cached": False},
    )


def test_speaker_name_store_is_order_independent(tmp_path: Path) -> None:
    store = SpeakerNameStore(directory=tmp_path)
    first = tmp_path / "part1.mp3"
    second = tmp_path / "part2.mp3"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    names = {"SPEAKER_00": "Alice", "SPEAKER_01": "Bob"}

    store.save([first, second], names)

    assert store.load([second, first]) == names
    assert store.path_for([first, second]).name.endswith(".speakers.json")


def test_speaker_name_store_apply_preserves_unknown_labels(tmp_path: Path) -> None:
    store = SpeakerNameStore(directory=tmp_path)
    source = tmp_path / "meeting.mp3"
    source.write_bytes(b"a")
    store.save([source], {"SPEAKER_00": "Alice"})

    merged = store.apply_to_names(
        [source],
        {"SPEAKER_00": "Speaker 1", "SPEAKER_01": "Speaker 2"},
    )

    assert merged["SPEAKER_00"] == "Alice"
    assert merged["SPEAKER_01"] == "Speaker 2"


def test_speaker_name_store_ignores_generic_names(tmp_path: Path) -> None:
    store = SpeakerNameStore(directory=tmp_path)
    source = tmp_path / "meeting.mp3"
    source.write_bytes(b"a")
    store.save(
        [source],
        {"SPEAKER_00": "Speaker 1", "SPEAKER_01": "SPEAKER_01", "SPEAKER_02": "Alice"},
    )
    assert store.load([source]) == {"SPEAKER_02": "Alice"}


def test_speaker_name_store_does_not_wipe_names_on_generic_save(
    tmp_path: Path,
) -> None:
    store = SpeakerNameStore(directory=tmp_path)
    source = tmp_path / "meeting.mp3"
    source.write_bytes(b"a")
    store.save([source], {"SPEAKER_00": "Alice"})
    store.save([source], {"SPEAKER_00": "Speaker 1"})
    assert store.load([source]) == {"SPEAKER_00": "Alice"}


def test_transcript_cache_saves_speaker_names_sidecar(tmp_path: Path) -> None:
    cache = TranscriptCache(directory=tmp_path)
    source = tmp_path / "meeting.mp4"
    source.touch()
    result = sample_result(str(source.resolve()))
    result.speakers = {"SPEAKER_00": "Alice"}

    cache.save(result)

    speakers_path = cache.speakers_path_for(source)
    assert speakers_path.is_file()
    loaded = cache.load(source)
    assert loaded is not None
    assert loaded.speakers["SPEAKER_00"] == "Alice"


def test_transcript_cache_prefers_sidecar_speaker_names(tmp_path: Path) -> None:
    cache = TranscriptCache(directory=tmp_path)
    source = tmp_path / "meeting.mp4"
    source.touch()
    result = sample_result(str(source.resolve()))
    result.speakers = {"SPEAKER_00": "Speaker 1"}
    cache.save(result)
    cache.speakers_path_for(source).write_text(
        '{"SPEAKER_00": "Alice"}',
        encoding="utf-8",
    )

    loaded = cache.load(source)
    assert loaded is not None
    assert loaded.speakers["SPEAKER_00"] == "Alice"


def test_transcript_cache_does_not_persist_generic_speaker_names(
    tmp_path: Path,
) -> None:
    cache = TranscriptCache(directory=tmp_path)
    source = tmp_path / "meeting.mp4"
    source.touch()
    result = sample_result(str(source.resolve()))
    result.speakers = {"SPEAKER_00": "Speaker 1", "SPEAKER_01": "SPEAKER_01"}
    cache.save(result)
    assert not cache.speakers_path_for(source).is_file()
    loaded = cache.load(source)
    assert loaded is not None
    assert loaded.speakers["SPEAKER_00"] == "Speaker 1"


def test_transcript_cache_keeps_custom_names_when_generics_are_saved(
    tmp_path: Path,
) -> None:
    cache = TranscriptCache(directory=tmp_path)
    source = tmp_path / "meeting.mp4"
    source.touch()
    result = sample_result(str(source.resolve()))
    result.speakers = {"SPEAKER_00": "Alice"}
    cache.save(result)
    result.speakers = {"SPEAKER_00": "Speaker 1"}
    cache.save(result)
    loaded = cache.load(source)
    assert loaded is not None
    assert loaded.speakers["SPEAKER_00"] == "Alice"
