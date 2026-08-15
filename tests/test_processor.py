import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from speaker_transcriber.audio.ffmpeg import MediaInfo
from speaker_transcriber.errors import ProcessingCancelled
from speaker_transcriber.models.model_manager import ModelManager
from speaker_transcriber.pipeline.processor import TranscriptionProcessor
from speaker_transcriber.pipeline.types import (
    DiarizationSegment,
    ProcessingOptions,
    RawSegment,
)


@pytest.fixture(autouse=True)
def bypass_trial_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "speaker_transcriber.pipeline.processor.probe_media_sources",
        lambda paths: MediaInfo(max(len(paths), 1) * 1.0, True),
    )
    monkeypatch.setattr(
        "speaker_transcriber.pipeline.processor.validate_trial_file_count",
        lambda paths: None,
    )
    monkeypatch.setattr(
        "speaker_transcriber.pipeline.processor.validate_trial_duration_consent",
        lambda full, cap: None,
    )


class FakeTranscriber:
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, audio_path, options, cancel, on_progress):
        self.calls += 1
        on_progress(1.0)
        return [
            RawSegment(
                0.0,
                1.0,
                "Hello",
                words=[{"word": "Hello", "start": 0.1, "end": 0.8}],
            )
        ], "en"


class FakeAligner:
    def __init__(self) -> None:
        self.model_name = None
        self.calls = 0

    def align(
        self,
        audio_path,
        segments,
        language,
        device,
        cancel,
        on_progress,
        model_name=None,
    ):
        self.calls += 1
        self.model_name = model_name
        on_progress(1.0)
        return [
            RawSegment(
                0.0,
                1.0,
                "Hello",
                words=[{"word": "Hello", "start": 0.05, "end": 0.9}],
            )
        ]


class FakeDiarizer:
    def __init__(self) -> None:
        self.calls = 0
        self.options = None

    def diarize(self, audio_path, options, device, cancel, on_progress):
        self.calls += 1
        self.options = options
        on_progress(1.0)
        return [DiarizationSegment(0.0, 1.0, "SPEAKER_00")]


@contextmanager
def fake_audio(source, cancel, on_progress, *, max_duration_seconds=None):
    on_progress(1.0)
    yield Path("audio.wav"), MediaInfo(1.0, True)


def test_processor_runs_mocked_pipeline(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "meeting.mp4"
    source.write_bytes(b"media")
    monkeypatch.setattr("speaker_transcriber.pipeline.processor.normalized_media", fake_audio)
    monkeypatch.setattr(
        "speaker_transcriber.huggingface_setup.prefetch_diarization_models",
        lambda token, model_id=None: None,
    )
    manager = ModelManager()
    monkeypatch.setattr(manager, "clear_cuda", lambda: None)
    monkeypatch.setattr(manager, "get_vram_info", lambda: (0, 0))
    processor = TranscriptionProcessor(
        manager,
        FakeTranscriber(),
        FakeAligner(),
        FakeDiarizer(),
    )
    updates = []
    result = processor.run(
        source,
        ProcessingOptions(hf_token="not-used"),
        on_progress=updates.append,
    )
    assert result.language == "en"
    assert result.diarization_available
    assert result.segments[0].speaker == "SPEAKER_00"
    assert processor.aligner.model_name is None
    transcribing = [item for item in updates if item.stage == "transcribing"]
    assert transcribing
    assert any(item.message == "Transcribing speech" for item in transcribing)
    assert transcribing[-1].stage_fraction == 1.0
    assert transcribing[-1].message == "Transcription complete"


def test_processor_forwards_alignment_model_name(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "meeting.mp4"
    source.write_bytes(b"media")
    monkeypatch.setattr("speaker_transcriber.pipeline.processor.normalized_media", fake_audio)
    monkeypatch.setattr(
        "speaker_transcriber.huggingface_setup.prefetch_diarization_models",
        lambda token, model_id=None: None,
    )
    manager = ModelManager()
    monkeypatch.setattr(manager, "clear_cuda", lambda: None)
    monkeypatch.setattr(manager, "get_vram_info", lambda: (0, 0))
    aligner = FakeAligner()
    processor = TranscriptionProcessor(
        manager,
        FakeTranscriber(),
        aligner,
        FakeDiarizer(),
    )
    processor.run(
        source,
        ProcessingOptions(
            hf_token="not-used",
            alignment_model="jonatasgrosman/wav2vec2-large-xlsr-53-english",
        ),
    )
    assert aligner.model_name == "jonatasgrosman/wav2vec2-large-xlsr-53-english"


def test_processor_accepts_multiple_sources(tmp_path: Path, monkeypatch) -> None:
    first = tmp_path / "part1.mp3"
    second = tmp_path / "part2.mp3"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    monkeypatch.setattr("speaker_transcriber.pipeline.processor.normalized_media", fake_audio)
    monkeypatch.setattr(
        "speaker_transcriber.huggingface_setup.prefetch_diarization_models",
        lambda token, model_id=None: None,
    )
    manager = ModelManager()
    monkeypatch.setattr(manager, "clear_cuda", lambda: None)
    monkeypatch.setattr(manager, "get_vram_info", lambda: (0, 0))
    processor = TranscriptionProcessor(
        manager,
        FakeTranscriber(),
        FakeAligner(),
        FakeDiarizer(),
    )
    result = processor.run(
        [first, second],
        ProcessingOptions(hf_token="not-used"),
    )
    assert result.source_files == [str(first.resolve()), str(second.resolve())]


def _mocked_processor(monkeypatch):
    monkeypatch.setattr("speaker_transcriber.pipeline.processor.normalized_media", fake_audio)
    monkeypatch.setattr(
        "speaker_transcriber.huggingface_setup.prefetch_diarization_models",
        lambda token, model_id=None: None,
    )
    manager = ModelManager()
    monkeypatch.setattr(manager, "clear_cuda", lambda: None)
    monkeypatch.setattr(manager, "get_vram_info", lambda: (0, 0))
    transcriber = FakeTranscriber()
    aligner = FakeAligner()
    diarizer = FakeDiarizer()
    processor = TranscriptionProcessor(manager, transcriber, aligner, diarizer)
    return processor, transcriber, aligner, diarizer


def test_processor_reuses_cached_transcription_and_diarization(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "meeting.mp4"
    source.write_bytes(b"media")
    processor, transcriber, aligner, diarizer = _mocked_processor(monkeypatch)
    cached_raw = [
        RawSegment(0.0, 1.0, "Hello", words=[{"word": "Hello", "start": 0.2, "end": 0.7}])
    ]
    cached_turns = [DiarizationSegment(0.0, 1.0, "SPEAKER_00")]
    result = processor.run(
        source,
        ProcessingOptions(
            hf_token="not-used",
            skip_transcription=True,
            skip_diarization=True,
            reuse_raw_segments=cached_raw,
            reuse_diarization=cached_turns,
            alignment_model="jonatasgrosman/wav2vec2-large-xlsr-53-english",
            language="en",
        ),
    )
    assert transcriber.calls == 0
    assert aligner.calls == 1
    assert diarizer.calls == 0
    assert result.raw_segments[0].words[0]["start"] == 0.2
    assert result.fallback_config["alignment_model"] == (
        "jonatasgrosman/wav2vec2-large-xlsr-53-english"
    )
    assert result.diarization[0].speaker == "SPEAKER_00"


def test_processor_reuses_cached_alignment_and_reruns_diarization(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "meeting.mp4"
    source.write_bytes(b"media")
    processor, transcriber, aligner, diarizer = _mocked_processor(monkeypatch)
    cached_raw = [RawSegment(0.0, 1.0, "Hello")]
    cached_aligned = [
        RawSegment(
            0.0,
            1.0,
            "Hello",
            words=[{"word": "Hello", "start": 0.05, "end": 0.9}],
        )
    ]
    result = processor.run(
        source,
        ProcessingOptions(
            hf_token="token",
            skip_transcription=True,
            skip_alignment=True,
            reuse_raw_segments=cached_raw,
            reuse_aligned_segments=cached_aligned,
            language="en",
            diarization_model="pyannote/speaker-diarization-community-1",
        ),
    )
    assert transcriber.calls == 0
    assert aligner.calls == 0
    assert diarizer.calls == 1
    assert result.raw_segments[0].text == "Hello"
    assert result.fallback_config["diarization_model"] == (
        "pyannote/speaker-diarization-community-1"
    )


def test_cancel_before_start(tmp_path: Path) -> None:
    source = tmp_path / "meeting.mp4"
    source.write_bytes(b"media")
    event = threading.Event()
    event.set()
    with pytest.raises(ProcessingCancelled):
        TranscriptionProcessor().run(source, ProcessingOptions(), event)
