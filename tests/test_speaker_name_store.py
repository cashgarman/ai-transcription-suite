from pathlib import Path

from speaker_transcriber.cache.speaker_name_store import SpeakerNameStore


def test_speaker_name_store_is_order_independent(tmp_path: Path) -> None:
    store = SpeakerNameStore(directory=tmp_path)
    first = tmp_path / "part1.mp3"
    second = tmp_path / "part2.mp3"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    names = {"SPEAKER_00": "Alice", "SPEAKER_01": "Bob"}

    store.save([first, second], names)

    assert store.load([second, first]) == names


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
