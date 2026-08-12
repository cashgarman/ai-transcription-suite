import json
from pathlib import Path

from speaker_transcriber.cache.transcript_cache import TranscriptCache
from speaker_transcriber.export.json_exporter import from_json_dict, to_json_dict
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


def test_json_round_trip_preserves_transcript_fields() -> None:
    original = sample_result()
    restored = from_json_dict(to_json_dict(original))
    assert restored.source_file == original.source_file
    assert restored.language == original.language
    assert restored.duration_seconds == original.duration_seconds
    assert restored.speakers == original.speakers
    assert restored.alignment_available == original.alignment_available
    assert restored.diarization_available == original.diarization_available
    assert restored.fallback_config == original.fallback_config
    assert len(restored.segments) == 1
    assert restored.segments[0].text == "Welcome."
    assert restored.segments[0].words[0].word == "Welcome"


def test_transcript_cache_uses_video_stem(tmp_path: Path) -> None:
    cache = TranscriptCache(directory=tmp_path)
    source = tmp_path / "videos" / "meeting.mp4"
    source.parent.mkdir()
    source.touch()
    result = sample_result(str(source.resolve()))

    cache.save(result)

    assert cache.path_for(source) == tmp_path / "meeting.json"
    assert cache.exists(source)
    loaded = cache.load(source)
    assert loaded is not None
    assert loaded.source_file == str(source.resolve())
    assert loaded.speakers["SPEAKER_00"] == "Alice"


def test_transcript_cache_returns_none_for_missing_file(tmp_path: Path) -> None:
    cache = TranscriptCache(directory=tmp_path)
    source = tmp_path / "missing.mp4"
    assert cache.load(source) is None


def test_transcript_cache_returns_none_for_invalid_json(tmp_path: Path) -> None:
    cache = TranscriptCache(directory=tmp_path)
    source = tmp_path / "broken.mp4"
    source.touch()
    cache.path_for(source).write_text("{not valid json", encoding="utf-8")
    assert cache.load(source) is None


def test_transcript_cache_delete(tmp_path: Path) -> None:
    cache = TranscriptCache(directory=tmp_path)
    source = tmp_path / "meeting.mp4"
    source.touch()
    cache.save(sample_result(str(source.resolve())))
    assert cache.exists(source)
    cache.delete(source)
    assert not cache.exists(source)


def test_to_json_dict_serializes_source_files() -> None:
    result = sample_result("/media/meeting-part1.mp3")
    result.source_files = ["/media/meeting-part1.mp3", "/media/meeting-part2.mp3"]
    payload = to_json_dict(result)
    assert payload["source_files"] == result.source_files
    restored = from_json_dict(json.loads(json.dumps(payload)))
    assert restored.source_files == result.source_files


def test_to_json_dict_serializes_source_file() -> None:
    payload = to_json_dict(sample_result("/media/meeting.mp4"))
    assert payload["source_file"] == "/media/meeting.mp4"
    assert payload["metadata"]["speaker_display_names"]["SPEAKER_00"] == "Alice"
    round_trip = json.loads(json.dumps(payload))
    assert from_json_dict(round_trip).source_file == "/media/meeting.mp4"


def test_metadata_speaker_names_round_trip() -> None:
    payload = to_json_dict(sample_result())
    payload["speakers"] = {"SPEAKER_00": "Speaker 1"}
    payload["metadata"]["speaker_display_names"] = {"SPEAKER_00": "Alice"}
    restored = from_json_dict(payload)
    assert restored.speakers["SPEAKER_00"] == "Alice"
