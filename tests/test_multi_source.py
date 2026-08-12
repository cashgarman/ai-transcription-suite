import json
from pathlib import Path

import pytest

from speaker_transcriber.audio import ffmpeg
from speaker_transcriber.audio.preprocessing import normalized_media
from speaker_transcriber.audio.sources import MediaSource
from speaker_transcriber.cache.transcript_cache import TranscriptCache
from speaker_transcriber.errors import ProcessingCancelled
from tests.test_transcript_cache import sample_result


def test_media_source_parse_accepts_tuple_of_paths(tmp_path: Path) -> None:
    first = tmp_path / "part1.mp3"
    second = tmp_path / "part2.mp3"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    source = MediaSource.parse((first, second))
    assert source.paths == (first.resolve(), second.resolve())
    first = tmp_path / "part1.mp3"
    second = tmp_path / "part2.mp3"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    source = MediaSource.parse([first, second])
    assert source.cache_key() == MediaSource.parse([first, second]).cache_key()
    assert source.cache_key() != MediaSource.parse([second, first]).cache_key()


def test_media_source_summary_label() -> None:
    source = MediaSource.parse(["/tmp/meeting-part1.mp3", "/tmp/meeting-part2.mp3"])
    assert source.summary_label() == "meeting-part1.mp3 (+ 1 more)"


def test_transcript_cache_uses_composite_key_for_multiple_files(tmp_path: Path) -> None:
    cache = TranscriptCache(directory=tmp_path)
    first = tmp_path / "meeting-part1.mp3"
    second = tmp_path / "meeting-part2.mp3"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    sources = [first, second]
    media_source = MediaSource.parse(sources)
    result = sample_result(media_source.source_file_for_result())
    result.source_files = media_source.source_files_for_result()

    cache.save(result)

    assert cache.path_for(sources) == tmp_path / f"{media_source.cache_key()}.json"
    assert cache.exists(sources)
    loaded = cache.load(sources)
    assert loaded is not None
    assert loaded.source_files == media_source.source_files_for_result()


def test_concat_wav_files_copies_single_chunk(tmp_path: Path) -> None:
    chunk = tmp_path / "chunk.wav"
    destination = tmp_path / "merged.wav"
    chunk.write_bytes(b"RIFFdemo")
    ffmpeg.concat_wav_files([chunk], destination, __import__("threading").Event())
    assert destination.read_bytes() == b"RIFFdemo"


def test_concat_wav_files_raises_when_cancelled(tmp_path: Path, monkeypatch) -> None:
    chunk = tmp_path / "chunk.wav"
    chunk.write_bytes(b"RIFFdemo")
    cancel = __import__("threading").Event()
    cancel.set()
    with pytest.raises(ProcessingCancelled):
        ffmpeg.concat_wav_files([chunk, chunk], tmp_path / "merged.wav", cancel)


def test_normalized_media_merges_multiple_sources(tmp_path: Path, monkeypatch) -> None:
    first = tmp_path / "part1.mp3"
    second = tmp_path / "part2.mp3"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    calls: list[Path] = []

    def fake_probe(source):
        return ffmpeg.MediaInfo(2.0, True)

    def fake_extract(source, destination, duration_seconds, cancel_event, on_progress=None):
        calls.append(Path(source))
        Path(destination).write_bytes(f"chunk-{Path(source).name}".encode())

    def fake_concat(sources, destination, cancel_event):
        Path(destination).write_bytes(b"".join(Path(source).read_bytes() for source in sources))

    monkeypatch.setattr(ffmpeg, "probe_media", fake_probe)
    monkeypatch.setattr(ffmpeg, "probe_media_sources", lambda sources: ffmpeg.MediaInfo(4.0, True))
    monkeypatch.setattr(ffmpeg, "extract_audio", fake_extract)
    monkeypatch.setattr(ffmpeg, "concat_wav_files", fake_concat)
    monkeypatch.setattr(
        "speaker_transcriber.audio.preprocessing.probe_media",
        fake_probe,
    )
    monkeypatch.setattr(
        "speaker_transcriber.audio.preprocessing.extract_audio",
        fake_extract,
    )
    monkeypatch.setattr(
        "speaker_transcriber.audio.preprocessing.concat_wav_files",
        fake_concat,
    )

    with normalized_media([first, second], __import__("threading").Event()) as (audio_path, media):
        assert audio_path.name == "audio.wav"
        assert media.duration_seconds == 4.0
        assert audio_path.read_bytes() == b"chunk-part1.mp3chunk-part2.mp3"

    assert calls == [first, second]
