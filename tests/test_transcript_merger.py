from speaker_transcriber.pipeline.transcript_merger import merge_words
from speaker_transcriber.pipeline.types import Word


def test_merges_neighbouring_words_from_same_speaker() -> None:
    words = [
        Word("Hello", 0.0, 0.4, "SPEAKER_00"),
        Word(",", 0.4, 0.5, "SPEAKER_00"),
        Word("world", 0.6, 1.0, "SPEAKER_00"),
    ]
    blocks = merge_words(words, gap_threshold_seconds=0.5, max_duration_seconds=10)
    assert len(blocks) == 1
    assert blocks[0].text == "Hello, world"


def test_speaker_change_starts_new_block() -> None:
    words = [
        Word("Hello", 0.0, 0.4, "SPEAKER_00"),
        Word("Hi", 0.5, 0.8, "SPEAKER_01"),
    ]
    assert len(merge_words(words)) == 2


def test_gap_and_max_duration_start_new_blocks() -> None:
    words = [
        Word("one", 0.0, 0.5, "SPEAKER_00"),
        Word("two", 2.0, 2.5, "SPEAKER_00"),
        Word("three", 3.0, 5.0, "SPEAKER_00"),
    ]
    blocks = merge_words(words, gap_threshold_seconds=0.5, max_duration_seconds=2.0)
    assert [block.text for block in blocks] == ["one", "two", "three"]
