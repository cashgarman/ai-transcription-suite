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

    cached = cache.path_for(source)
    assert cached.parent == tmp_path
    assert cached.name.startswith("meeting_")
    assert cached.suffix == ".json"
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
    cache.save_summary(source, "# Notes\n\nCached meeting notes.")
    assert cache.exists(source)
    assert cache.speakers_path_for(source).is_file()
    assert cache.summary_exists(source)
    cache.delete(source)
    assert not cache.exists(source)
    assert not cache.speakers_path_for(source).is_file()
    assert not cache.summary_exists(source)


def test_transcript_cache_saves_and_loads_summary(tmp_path: Path) -> None:
    cache = TranscriptCache(directory=tmp_path)
    source = tmp_path / "meeting.mp4"
    source.touch()
    markdown = "# Meeting Notes\n\n**Participants:** Alex"
    cache.save_summary(source, markdown)
    summary_path = cache.summary_path_for(source)
    assert summary_path.parent == tmp_path
    assert summary_path.name.startswith("meeting_")
    assert summary_path.name.endswith(".summary.meeting_summary.md")
    assert cache.summary_exists(source)
    assert cache.load_summary(source) == markdown
    cache.save_summary(source, "   ")
    assert cache.load_summary(source) is None
    assert not cache.summary_exists(source)


def test_each_style_keeps_its_own_summary(tmp_path: Path) -> None:
    cache = TranscriptCache(directory=tmp_path)
    source = tmp_path / "meeting.mp4"
    source.touch()
    cache.save_summary(source, "# Notes", "meeting_summary")
    cache.save_summary(source, "# Pitch", "pitch_deck")
    assert cache.load_summary(source, "meeting_summary") == "# Notes"
    assert cache.load_summary(source, "pitch_deck") == "# Pitch"
    assert not cache.summary_exists(source, "internal_newsletter")
    assert cache.load_summary(source, "internal_newsletter") is None


def test_unknown_style_reads_the_default_summary(tmp_path: Path) -> None:
    cache = TranscriptCache(directory=tmp_path)
    source = tmp_path / "meeting.mp4"
    source.touch()
    cache.save_summary(source, "# Notes")
    assert cache.load_summary(source, "not-a-style") == "# Notes"


def test_legacy_summary_file_reads_as_meeting_notes(tmp_path: Path) -> None:
    cache = TranscriptCache(directory=tmp_path)
    source = tmp_path / "meeting.mp4"
    source.touch()
    legacy = cache.legacy_summary_path_for(source)
    legacy.write_text("# Legacy Notes\n", encoding="utf-8")
    assert cache.summary_exists(source)
    assert cache.load_summary(source) == "# Legacy Notes"
    assert not cache.summary_exists(source, "pitch_deck")
    cache.save_summary(source, "# Fresh Notes")
    assert not legacy.is_file()
    assert cache.load_summary(source) == "# Fresh Notes"


def test_delete_removes_every_style_summary(tmp_path: Path) -> None:
    cache = TranscriptCache(directory=tmp_path)
    source = tmp_path / "meeting.mp4"
    source.touch()
    cache.legacy_summary_path_for(source).write_text("# Legacy\n", encoding="utf-8")
    cache.save_summary(source, "# Pitch", "pitch_deck")
    cache.save_summary(source, "# Standup", "standup_meeting")
    cache.delete(source)
    assert cache.summary_paths(source) == []


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


def _recording(directory: Path, name: str, contents: bytes) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(contents)
    return path


def test_same_filename_in_two_folders_does_not_share_a_cache(tmp_path: Path) -> None:
    cache = TranscriptCache(directory=tmp_path / "cache")
    first = _recording(tmp_path / "monday", "meeting.mp4", b"first")
    second = _recording(tmp_path / "tuesday", "meeting.mp4", b"second-recording")

    cache.save(sample_result(str(first.resolve())))

    assert cache.path_for(first) != cache.path_for(second)
    assert cache.exists(first)
    assert not cache.exists(second)


def test_replacing_a_recording_invalidates_its_cache(tmp_path: Path) -> None:
    cache = TranscriptCache(directory=tmp_path / "cache")
    source = _recording(tmp_path, "meeting.mp4", b"original")
    cache.save(sample_result(str(source.resolve())))
    assert cache.exists(source)

    source.write_bytes(b"a different recording entirely")

    assert not cache.exists(source)


def test_legacy_stem_named_cache_is_adopted(tmp_path: Path) -> None:
    directory = tmp_path / "cache"
    directory.mkdir()
    source = _recording(tmp_path, "meeting.mp4", b"audio")
    result = sample_result(str(source.resolve()))
    (directory / "meeting.json").write_text(
        json.dumps(to_json_dict(result)), encoding="utf-8"
    )
    (directory / "meeting.summary.meeting_summary.md").write_text(
        "# Notes\n", encoding="utf-8"
    )

    cache = TranscriptCache(directory=directory)

    assert cache.exists(source)
    loaded = cache.load(source)
    assert loaded is not None
    assert loaded.segments[0].text == "Welcome."
    assert cache.load_summary(source) == "# Notes"
    assert not (directory / "meeting.json").exists()


def test_legacy_cache_for_a_different_recording_is_left_alone(tmp_path: Path) -> None:
    directory = tmp_path / "cache"
    directory.mkdir()
    stranger = _recording(tmp_path / "elsewhere", "meeting.mp4", b"other")
    (directory / "meeting.json").write_text(
        json.dumps(to_json_dict(sample_result(str(stranger.resolve())))),
        encoding="utf-8",
    )
    source = _recording(tmp_path / "mine", "meeting.mp4", b"mine")

    cache = TranscriptCache(directory=directory)

    assert not cache.exists(source)
    assert (directory / "meeting.json").exists()
