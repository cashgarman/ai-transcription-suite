from __future__ import annotations

import threading
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication, QDialog

from speaker_transcriber.audio.tts.export import export_rendered_mp3
from speaker_transcriber.audio.tts.queue import SegmentPlaybackQueue
from speaker_transcriber.audio.tts.renderer import render_transcript
from speaker_transcriber.audio.tts.types import RenderedSegment, SystemVoice
from speaker_transcriber.audio.tts.tempo import atempo_filter_graph, clamp_playback_rate
from speaker_transcriber.audio.tts.voices import assign_voices, speakers_in_appearance_order
from speaker_transcriber.audio.tts.wavutil import write_silence_wav
from speaker_transcriber.errors import ProcessingCancelled, TtsError
from speaker_transcriber.pipeline.types import TranscriptResult, TranscriptSegment
from speaker_transcriber.ui.transcript_tts_bar import TranscriptTtsBar
from speaker_transcriber.ui.transcript_tts_render_dialog import TranscriptTtsRenderDialog
from speaker_transcriber.ui.transcript_panel import TranscriptPanel
from speaker_transcriber.ui.transcript_view import SegmentBlockData, TranscriptView


def _voices() -> list[SystemVoice]:
    return [
        SystemVoice("Microsoft David", "Microsoft David", "male"),
        SystemVoice("Microsoft Mark", "Microsoft Mark", "male"),
        SystemVoice("Microsoft Zira", "Microsoft Zira", "female"),
        SystemVoice("Microsoft Hazel", "Microsoft Hazel", "female"),
    ]


def _result(*lines: tuple[str, str]) -> TranscriptResult:
    segments = [
        TranscriptSegment(float(index), float(index) + 1.0, speaker, text)
        for index, (speaker, text) in enumerate(lines)
    ]
    speakers = {speaker: speaker for speaker, _text in lines}
    return TranscriptResult(
        source_file="meeting.mp4",
        language="en",
        duration_seconds=float(len(segments)),
        speakers=speakers,
        segments=segments,
    )


class FakeTtsBackend:
    def __init__(self, voices: list[SystemVoice] | None = None) -> None:
        self.voices = voices or _voices()
        self.spoken: list[tuple[str, str]] = []

    def list_voices(self) -> list[SystemVoice]:
        return list(self.voices)

    def synthesize(self, text: str, voice_id: str, output_wav: Path) -> None:
        self.spoken.append((text, voice_id))
        write_silence_wav(output_wav, duration_seconds=0.05)

    def close(self) -> None:
        return None


def _application() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def test_assign_voices_alternates_male_and_female_variants() -> None:
    mapping = assign_voices(
        ["SPEAKER_00", "SPEAKER_01", "SPEAKER_02", "SPEAKER_03"],
        _voices(),
    )
    assert mapping["SPEAKER_00"].gender == "male"
    assert mapping["SPEAKER_00"].id == "Microsoft David"
    assert mapping["SPEAKER_01"].gender == "female"
    assert mapping["SPEAKER_01"].id == "Microsoft Zira"
    assert mapping["SPEAKER_02"].id == "Microsoft Mark"
    assert mapping["SPEAKER_03"].id == "Microsoft Hazel"


def test_assign_voices_rotates_when_one_gender_is_missing() -> None:
    females = [voice for voice in _voices() if voice.gender == "female"]
    mapping = assign_voices(["A", "B", "C"], females)
    assert mapping["A"].id == "Microsoft Zira"
    assert mapping["B"].id == "Microsoft Zira"
    assert mapping["C"].id == "Microsoft Hazel"


def test_assign_voices_requires_installed_voices() -> None:
    with pytest.raises(TtsError):
        assign_voices(["SPEAKER_00"], [])


def test_assign_voices_respects_speaker_genders() -> None:
    mapping = assign_voices(
        ["SPEAKER_00", "SPEAKER_01", "SPEAKER_02"],
        _voices(),
        genders={
            "SPEAKER_00": "female",
            "SPEAKER_01": "female",
            "SPEAKER_02": "male",
        },
    )
    assert mapping["SPEAKER_00"].gender == "female"
    assert mapping["SPEAKER_01"].gender == "female"
    assert mapping["SPEAKER_00"].id == "Microsoft Zira"
    assert mapping["SPEAKER_01"].id == "Microsoft Hazel"
    assert mapping["SPEAKER_02"].gender == "male"
    assert mapping["SPEAKER_02"].id == "Microsoft David"


def test_renderer_uses_speaker_genders_for_voice_assignment(tmp_path) -> None:
    backend = FakeTtsBackend()
    result = _result(("SPEAKER_00", "Hello there"), ("SPEAKER_01", "Welcome back"))
    result.speaker_genders = {"SPEAKER_00": "female", "SPEAKER_01": "male"}
    render_transcript(result, backend=backend, work_dir=tmp_path / "gendered")
    assert backend.spoken[0][1] == "Microsoft Zira"
    assert backend.spoken[1][1] == "Microsoft David"


def test_speakers_follow_first_appearance() -> None:
    result = _result(
        ("SPEAKER_01", "Hello"),
        ("SPEAKER_00", "Hi"),
        ("SPEAKER_01", "Again"),
    )
    assert speakers_in_appearance_order(result) == ["SPEAKER_01", "SPEAKER_00"]


def test_clamp_playback_rate_stays_within_quarter_to_four() -> None:
    assert clamp_playback_rate(1) == 1.0
    assert clamp_playback_rate(0.1) == 0.25
    assert clamp_playback_rate(9) == 4.0
    assert clamp_playback_rate(1.24) == 1.25


def test_atempo_chain_keeps_each_stage_between_half_and_double() -> None:
    assert atempo_filter_graph(1.0) is None
    assert atempo_filter_graph(1.5) == "atempo=1.5"
    assert atempo_filter_graph(4.0) == "atempo=2,atempo=2"
    assert atempo_filter_graph(0.25) == "atempo=0.5,atempo=0.5"


def test_rewind_moves_to_previous_segment_and_stops_at_zero() -> None:
    queue = SegmentPlaybackQueue(3)
    queue.index = 2
    assert queue.rewind() == 1
    assert queue.rewind() == 0
    assert queue.rewind() == 0


def test_advance_returns_none_after_last_segment() -> None:
    queue = SegmentPlaybackQueue(2)
    assert queue.advance() == 1
    assert queue.advance() is None


def test_renderer_writes_one_wav_per_segment(tmp_path) -> None:
    backend = FakeTtsBackend()
    result = _result(("SPEAKER_00", "Hello there"), ("SPEAKER_01", "Welcome back"))
    progress: list[tuple[int, int]] = []
    rendered = render_transcript(
        result,
        backend=backend,
        work_dir=tmp_path / "out",
        progress_cb=lambda current, total, _message: progress.append((current, total)),
    )
    assert len(rendered) == 2
    assert all(segment.wav_path.is_file() for segment in rendered)
    assert [text for text, _voice in backend.spoken] == ["Hello there", "Welcome back"]
    assert backend.spoken[0][1] != backend.spoken[1][1]
    assert progress[-1] == (2, 2)


def test_renderer_reuses_cached_wavs(tmp_path) -> None:
    backend = FakeTtsBackend()
    result = _result(("SPEAKER_00", "Cached line"))
    work_dir = tmp_path / "cache"
    first = render_transcript(result, backend=backend, work_dir=work_dir)
    spoken_after_first = list(backend.spoken)
    second = render_transcript(result, backend=backend, work_dir=work_dir)
    assert [segment.wav_path for segment in second] == [segment.wav_path for segment in first]
    assert backend.spoken == spoken_after_first


def test_renderer_honors_cancel(tmp_path) -> None:
    backend = FakeTtsBackend()
    result = _result(("SPEAKER_00", "One"), ("SPEAKER_01", "Two"))
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ProcessingCancelled):
        render_transcript(
            result,
            backend=backend,
            work_dir=tmp_path / "out",
            cancel_event=cancel,
        )


def test_export_concatenates_then_encodes(tmp_path, monkeypatch) -> None:
    from speaker_transcriber.audio.tts import export as export_mod

    wav_a = tmp_path / "0.wav"
    wav_b = tmp_path / "1.wav"
    write_silence_wav(wav_a)
    write_silence_wav(wav_b)
    destination = tmp_path / "out.mp3"
    calls: list[str] = []

    def fake_concat(sources, dest, cancel_event) -> None:
        calls.append("concat")
        Path(dest).write_bytes(b"wav")

    def fake_encode(source, dest, cancel_event) -> None:
        calls.append("encode")
        Path(dest).write_bytes(b"mp3")

    monkeypatch.setattr(export_mod, "concat_wav_files", fake_concat)
    monkeypatch.setattr(export_mod, "encode_wav_to_mp3", fake_encode)
    segments = [
        RenderedSegment(0, "SPEAKER_00", wav_a, 0.1, 0.0),
        RenderedSegment(1, "SPEAKER_01", wav_b, 0.1, 1.0),
    ]
    export_rendered_mp3(segments, destination, threading.Event())
    assert calls == ["concat", "encode"]
    assert destination.read_bytes() == b"mp3"
    assert not destination.with_name("out_concat.wav").exists()


def test_tts_bar_includes_voice_model_picker() -> None:
    _application()
    from speaker_transcriber.config import AppSettings
    from speaker_transcriber.ui.transcript_tts_models import populate_tts_model_combo

    bar = TranscriptTtsBar()
    populate_tts_model_combo(bar.model_combo, AppSettings())
    assert bar.model_combo is not None
    assert bar.model_combo.count() > 0
    assert bar.current_tts_model()
    bar.close()


def test_tts_bar_enables_playback_only_after_prepare() -> None:
    _application()
    bar = TranscriptTtsBar()
    bar.set_state(has_transcript=True, prepared=False)
    assert bar.prepare_button.isEnabled()
    assert not bar.play_button.isEnabled()
    assert not bar.export_button.isEnabled()
    bar.set_state(has_transcript=True, prepared=True)
    assert bar.play_button.isEnabled()
    assert bar.export_button.isEnabled()
    assert bar.status_label.text() == "Ready"
    bar.close()


def test_tts_bar_speed_slider_covers_quarter_to_four() -> None:
    _application()
    bar = TranscriptTtsBar()
    rates: list[float] = []
    bar.rate_changed.connect(rates.append)
    bar.speed_slider.setValue(25)
    bar._emit_rate()
    bar.speed_slider.setValue(400)
    bar._emit_rate()
    assert bar.speed_slider.minimum() == 25
    assert bar.speed_slider.maximum() == 400
    assert rates[-2:] == [0.25, 4.0]
    assert bar.speed_value.text() == "4.00×"
    bar.close()


def test_panel_keeps_play_disabled_until_audio_is_prepared() -> None:
    _application()
    panel = TranscriptPanel()
    assert not panel.tts_bar.prepare_button.isEnabled()
    panel.set_result(_result(("SPEAKER_00", "Hello")))
    assert panel.tts_bar.prepare_button.isEnabled()
    assert not panel.tts_bar.play_button.isEnabled()
    assert not panel.tts_bar.export_button.isEnabled()
    panel.close()


def test_tts_shutdown_stops_playback_and_is_idempotent() -> None:
    _application()
    panel = TranscriptPanel()
    panel.set_result(_result(("SPEAKER_00", "Hello")))
    panel.tts.shutdown()
    panel.tts.shutdown()
    assert not panel.tts_bar.play_button.isEnabled()
    panel.close()


def test_render_dialog_updates_progress() -> None:
    _application()
    dialog = TranscriptTtsRenderDialog()
    dialog.set_progress(3, 10, "Rendering segment 4 of 10…")
    assert dialog.progress_bar.value() == 3
    assert dialog.progress_bar.maximum() == 10
    assert "4 of 10" in dialog.status_label.text()
    dialog.finish()


def test_render_dialog_finish_closes_without_cancelling() -> None:
    _application()
    dialog = TranscriptTtsRenderDialog()
    cancelled: list[bool] = []
    dialog.cancel_requested.connect(lambda: cancelled.append(True))
    dialog.show()
    dialog.set_progress(10, 10, "Audio is ready")
    dialog.finish()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert not dialog.isVisible()
    assert cancelled == []
    assert dialog.status_label.text() == "Audio is ready"


def test_render_dialog_reject_requests_cancel_until_finish() -> None:
    _application()
    dialog = TranscriptTtsRenderDialog()
    cancelled: list[bool] = []
    dialog.cancel_requested.connect(lambda: cancelled.append(True))
    dialog.show()
    dialog.reject()
    assert cancelled == [True]
    assert dialog.isVisible()
    assert dialog.status_label.text() == "Cancelling…"
    dialog.finish()
    assert not dialog.isVisible()


def test_render_worker_emits_finished(tmp_path) -> None:
    from speaker_transcriber.ui.transcript_tts_worker import TranscriptTtsRenderWorker

    application = _application()
    result = _result(("SPEAKER_00", "Hello"), ("SPEAKER_01", "There"))
    worker = TranscriptTtsRenderWorker(
        result,
        backend=FakeTtsBackend(),
        cache_root=tmp_path,
    )
    finished: list[list[RenderedSegment]] = []
    worker.render_finished.connect(finished.append)
    worker.start()
    worker.wait(8000)
    application.processEvents()
    assert len(finished) == 1
    assert len(finished[0]) == 2


def _playback_starts(view: TranscriptView) -> set[float]:
    starts: set[float] = set()
    for selection in view.extraSelections():
        data = selection.cursor.block().userData()
        if isinstance(data, SegmentBlockData):
            starts.add(data.start)
    return starts


def test_playback_highlights_the_spoken_turn() -> None:
    _application()
    view = TranscriptView()
    view.set_result(
        _result(("SPEAKER_00", "Hello there"), ("SPEAKER_01", "Welcome back"))
    )
    view.set_playback_time(1.0)
    assert _playback_starts(view) == {1.0}
    view.clear_playback()
    assert _playback_starts(view) == set()
    view.close()


def test_playback_follow_scrolls_to_later_turns() -> None:
    application = _application()
    lines = [
        ("SPEAKER_00", f"Turn number {index} with extra padding words.")
        for index in range(40)
    ]
    view = TranscriptView()
    view.set_result(_result(*lines))
    view.resize(420, 180)
    view.show()
    application.processEvents()
    assert view.verticalScrollBar().maximum() > 0
    view.set_playback_time(0.0)
    application.processEvents()
    first = view.verticalScrollBar().value()
    view.set_playback_time(39.0)
    application.processEvents()
    assert view.verticalScrollBar().value() > first
    view.close()


def test_panel_follows_tts_segment_signals() -> None:
    _application()
    panel = TranscriptPanel()
    panel.set_result(_result(("SPEAKER_00", "Hello"), ("SPEAKER_01", "There")))
    panel.tts.segment_started.emit(1.0)
    assert _playback_starts(panel.transcript_view) == {1.0}
    panel.tts.playback_stopped.emit()
    assert _playback_starts(panel.transcript_view) == set()
    panel.close()


def test_stopping_playback_clears_the_spoken_highlight() -> None:
    _application()
    panel = TranscriptPanel()
    panel.set_result(_result(("SPEAKER_00", "Hello"), ("SPEAKER_01", "There")))
    stopped: list[bool] = []
    panel.tts.playback_stopped.connect(lambda: stopped.append(True))
    panel.tts.segment_started.emit(0.0)
    assert _playback_starts(panel.transcript_view) == {0.0}
    panel.tts._on_state_changed("stopped")
    assert stopped == [True]
    assert _playback_starts(panel.transcript_view) == set()
    panel.close()


def test_playback_skips_filtered_out_speakers() -> None:
    _application()
    view = TranscriptView()
    view.set_result(_result(("SPEAKER_00", "Hello"), ("SPEAKER_01", "There")))
    view.set_speaker_filter("SPEAKER_00")
    view.set_playback_time(1.0)
    assert _playback_starts(view) == set()
    view.set_playback_time(0.0)
    assert _playback_starts(view) == {0.0}
    view.close()


def test_playback_highlight_covers_a_turn_while_another_speaker_is_selected() -> None:
    _application()
    view = TranscriptView()
    view.set_result(_result(("SPEAKER_00", "Hello"), ("SPEAKER_01", "There")))
    view.highlight_speaker("SPEAKER_00")
    view.set_playback_time(1.0)
    starts = _playback_starts(view)
    assert 0.0 in starts
    assert 1.0 in starts
    view.close()

