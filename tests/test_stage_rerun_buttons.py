from queue import Queue
from pathlib import Path

from PySide6.QtWidgets import QApplication

from speaker_transcriber.cache.transcript_cache import TranscriptCache
from speaker_transcriber.config import SettingsStore
from speaker_transcriber.models.model_catalog import (
    DEFAULT_DIARIZATION_MODEL,
    RECOMMENDED_ALIGNMENT_MODEL,
)
from speaker_transcriber.pipeline.types import (
    DiarizationSegment,
    RawSegment,
    TranscriptResult,
    TranscriptSegment,
    Word,
)
from speaker_transcriber.ui.main_window import MainWindow


def _application() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def _cached_result(source: Path) -> TranscriptResult:
    return TranscriptResult(
        source_file=str(source.resolve()),
        language="en",
        duration_seconds=1.0,
        speakers={"SPEAKER_00": "Ada"},
        segments=[
            TranscriptSegment(
                0.0,
                1.0,
                "SPEAKER_00",
                "Hello",
                [Word("Hello", 0.0, 0.8, "SPEAKER_00")],
            )
        ],
        alignment_available=True,
        diarization_available=True,
        fallback_config={
            "model": "distil-large-v3",
            "alignment_model": "auto",
            "diarization_model": DEFAULT_DIARIZATION_MODEL,
        },
        raw_segments=[RawSegment(0.0, 1.0, "Hello")],
        diarization=[DiarizationSegment(0.0, 1.0, "SPEAKER_00")],
    )


def _window_with_cache(tmp_path: Path) -> tuple[MainWindow, Path]:
    _application()
    window = MainWindow(SettingsStore(tmp_path), Queue())
    cache_dir = tmp_path / "transcripts"
    window.transcript_cache = TranscriptCache(directory=cache_dir)
    source = tmp_path / "meeting.mp4"
    source.write_bytes(b"media")
    result = _cached_result(source)
    window.transcript_cache.save(result)
    window.result = result
    window._current_sources = lambda: [source]
    window._displayed_source_key = lambda: (str(source.resolve()),)
    window._validate_source_input = lambda: [source]
    return window, source


def test_stage_rerun_buttons_enable_only_when_model_changes(tmp_path: Path) -> None:
    window, _source = _window_with_cache(tmp_path)
    window.alignment_combo.select_preferred(["auto"])
    window.diarization_combo.select_preferred([DEFAULT_DIARIZATION_MODEL])
    window._update_cache_controls()
    assert window.retranscribe_button.isEnabled()
    assert not window.realign_button.isEnabled()
    assert not window.rediarize_button.isEnabled()

    window.alignment_combo.select_preferred([RECOMMENDED_ALIGNMENT_MODEL])
    window._update_cache_controls()
    assert window.realign_button.isEnabled()
    assert not window.rediarize_button.isEnabled()

    window.alignment_combo.select_preferred(["auto"])
    window.diarization_combo.select_preferred(["pyannote/speaker-diarization-3.0"])
    window._update_cache_controls()
    assert not window.realign_button.isEnabled()
    assert window.rediarize_button.isEnabled()


def test_realign_reuses_cached_transcription_and_diarization(tmp_path: Path) -> None:
    window, source = _window_with_cache(tmp_path)
    captured: dict[str, object] = {}

    def fake_run(sources, **kwargs):
        captured["sources"] = sources
        captured["options"] = kwargs["options"]

    window._run_transcription = fake_run
    window._realign()
    options = captured["options"]
    assert captured["sources"] == [source]
    assert options.skip_transcription
    assert not options.skip_alignment
    assert options.skip_diarization
    assert options.reuse_raw_segments
    assert options.reuse_diarization
    assert options.language == "en"
    assert options.model == "distil-large-v3"


def test_rediarize_reuses_cached_transcription_and_alignment(tmp_path: Path) -> None:
    window, _source = _window_with_cache(tmp_path)
    captured: dict[str, object] = {}

    def fake_run(sources, **kwargs):
        captured["options"] = kwargs["options"]

    window._run_transcription = fake_run
    window._rediarize()
    options = captured["options"]
    assert options.skip_transcription
    assert options.skip_alignment
    assert not options.skip_diarization
    assert options.reuse_aligned_segments
    assert options.alignment_model == "auto"
