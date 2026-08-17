from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QMessageBox, QVBoxLayout, QWidget

from speaker_transcriber.audio.tts.playback import TranscriptTtsPlayer
from speaker_transcriber.audio.tts.types import RenderedSegment
from speaker_transcriber.config import SettingsStore
from speaker_transcriber.pipeline.types import TranscriptResult
from speaker_transcriber.ui.transcript_tts_bar import TranscriptTtsBar
from speaker_transcriber.ui.transcript_tts_models import (
    open_add_tts_models_dialog,
    populate_tts_model_combo,
    selected_tts_model_requires_download,
)
from speaker_transcriber.ui.transcript_tts_render_dialog import TranscriptTtsRenderDialog
from speaker_transcriber.ui.transcript_tts_worker import (
    TranscriptTtsExportWorker,
    TranscriptTtsRenderWorker,
)


class TranscriptTtsController(QWidget):
    """Prepare / play / export toolbar shared by the main app and Prompt Lab."""

    segment_started = Signal(float)
    playback_stopped = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        settings_store: SettingsStore | None = None,
        include_voice_model: bool = True,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._settings_store = settings_store or SettingsStore()
        self._settings = self._settings_store.load()
        self.bar = TranscriptTtsBar(include_voice_model=include_voice_model)
        layout.addWidget(self.bar)
        populate_tts_model_combo(self.bar.model_combo, self._settings)

        self._result: TranscriptResult | None = None
        self._rendered: list[RenderedSegment] = []
        self._playing = False
        self._paused = False
        self._render_worker: TranscriptTtsRenderWorker | None = None
        self._export_worker: TranscriptTtsExportWorker | None = None
        self._progress_dialog: TranscriptTtsRenderDialog | None = None
        self._player = TranscriptTtsPlayer(self)
        self._player.segment_changed.connect(self._on_segment_changed)
        self._player.state_changed.connect(self._on_state_changed)
        self._player.finished.connect(self._on_finished)
        self._player.error.connect(self._on_error)

        self.bar.prepare_requested.connect(self._on_prepare_audio)
        self.bar.play_requested.connect(self._player.play)
        self.bar.pause_requested.connect(self._player.pause)
        self.bar.stop_requested.connect(self._player.stop)
        self.bar.rewind_requested.connect(self._player.rewind)
        self.bar.export_requested.connect(self._on_export_mp3)
        self.bar.rate_changed.connect(self._player.set_rate)
        self.bar.model_changed.connect(self._on_tts_model_changed)
        self.bar.add_tts_models_requested.connect(self._open_add_tts_models)
        self._player.set_rate(self.bar.playback_rate())
        self._refresh_bar()

    @property
    def tts_bar(self) -> TranscriptTtsBar:
        return self.bar

    def set_result(self, result: TranscriptResult | None) -> None:
        self._reset()
        self._result = result
        self._refresh_bar()

    def shutdown(self) -> None:
        """Stop playback and cancel in-flight render/export work."""
        self._reset()

    def _reset(self) -> None:
        self._player.stop()
        self._cancel_render_worker()
        self._cancel_export_worker()
        self._close_progress_dialog()
        self._rendered = []
        self._playing = False
        self._paused = False

    def _refresh_bar(self, status: str | None = None) -> None:
        self.bar.set_state(
            has_transcript=bool(self._result and self._result.segments),
            prepared=bool(self._rendered),
            rendering=self._render_worker is not None,
            exporting=self._export_worker is not None,
            playing=self._playing,
            paused=self._paused,
            status=status,
            segment_index=self._player.index,
            segment_count=len(self._rendered),
        )

    def _on_prepare_audio(self) -> None:
        if self._result is None or not self._result.segments:
            return
        if self._render_worker is not None:
            return
        model_id = self.bar.current_tts_model()
        if selected_tts_model_requires_download(model_id):
            QMessageBox.warning(
                self,
                "Voice model not installed",
                "The selected Piper voice is not downloaded yet.\n\n"
                "Choose Add Models… in the voice model picker to download it.",
            )
            return
        self._player.stop()
        worker = TranscriptTtsRenderWorker(
            self._result,
            self,
            tts_model=model_id,
            extra_tts_models=self._settings.extra_tts_models,
        )
        self._render_worker = worker
        dialog = TranscriptTtsRenderDialog(self)
        self._progress_dialog = dialog
        worker.progress.connect(dialog.set_progress)
        worker.render_finished.connect(self._on_render_finished)
        worker.failed.connect(self._on_render_failed)
        worker.cancelled.connect(self._on_render_cancelled)
        dialog.cancel_requested.connect(worker.cancel)
        self._refresh_bar()
        worker.start()
        dialog.exec()

    def _on_render_finished(self, segments: object) -> None:
        self._rendered = list(segments)  # type: ignore[arg-type]
        self._player.load(self._rendered)
        self._finish_render_job()
        self._refresh_bar()

    def _on_render_failed(self, message: str) -> None:
        self._finish_render_job()
        self._refresh_bar()
        QMessageBox.critical(self, "Could not prepare audio", message)

    def _on_render_cancelled(self) -> None:
        self._finish_render_job()
        self._refresh_bar()

    def _finish_render_job(self) -> None:
        worker = self._render_worker
        self._render_worker = None
        self._close_progress_dialog()
        if worker is not None:
            worker.wait(8000)

    def _on_export_mp3(self) -> None:
        if not self._rendered or self._result is None:
            return
        stem = Path(self._result.source_file).stem or "transcript"
        suggested = str(Path(self._result.source_file).with_name(f"{stem}-tts.mp3"))
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Export TTS audio",
            suggested,
            "MP3 (*.mp3)",
        )
        if not destination:
            return
        path = Path(destination)
        if path.suffix.lower() != ".mp3":
            path = path.with_suffix(".mp3")
        worker = TranscriptTtsExportWorker(self._rendered, path, self)
        self._export_worker = worker
        dialog = TranscriptTtsRenderDialog(self, title="Exporting MP3")
        dialog.set_progress(0, 0, "Writing MP3…")
        self._progress_dialog = dialog
        worker.export_finished.connect(self._on_export_finished)
        worker.failed.connect(self._on_export_failed)
        worker.cancelled.connect(self._on_export_cancelled)
        dialog.cancel_requested.connect(worker.cancel)
        self._refresh_bar()
        worker.start()
        dialog.exec()

    def _on_export_finished(self, destination: str) -> None:
        self._finish_export_job()
        self._refresh_bar()
        QMessageBox.information(self, "Export complete", f"Saved MP3 to:\n{destination}")

    def _on_export_failed(self, message: str) -> None:
        self._finish_export_job()
        self._refresh_bar()
        QMessageBox.critical(self, "Export failed", message)

    def _on_export_cancelled(self) -> None:
        self._finish_export_job()
        self._refresh_bar()

    def _finish_export_job(self) -> None:
        worker = self._export_worker
        self._export_worker = None
        self._close_progress_dialog()
        if worker is not None:
            worker.wait(8000)

    def _close_progress_dialog(self) -> None:
        dialog = self._progress_dialog
        self._progress_dialog = None
        if dialog is None:
            return
        dialog.finish()

    def _cancel_render_worker(self) -> None:
        worker = self._render_worker
        if worker is None:
            return
        worker.cancel()
        worker.wait(8000)
        self._render_worker = None

    def _cancel_export_worker(self) -> None:
        worker = self._export_worker
        if worker is None:
            return
        worker.cancel()
        worker.wait(8000)
        self._export_worker = None

    def _on_segment_changed(self, index: int) -> None:
        if 0 <= index < len(self._rendered):
            self.segment_started.emit(self._rendered[index].start)
        self._refresh_bar()

    def _on_state_changed(self, state: str) -> None:
        self._playing = state == "playing"
        self._paused = state == "paused"
        self._refresh_bar()
        if state == "stopped":
            self.playback_stopped.emit()

    def _on_finished(self) -> None:
        self._playing = False
        self._paused = False
        self._refresh_bar()

    def _on_error(self, message: str) -> None:
        self._playing = False
        self._paused = False
        self._refresh_bar()
        QMessageBox.critical(self, "Playback failed", message)

    def _on_tts_model_changed(self, model_id: str) -> None:
        if self._settings.tts_model == model_id:
            return
        self._settings.tts_model = model_id
        self._settings_store.save(self._settings)
        self._rendered = []
        self._player.stop()
        self._refresh_bar()

    def _open_add_tts_models(self) -> None:
        downloaded = open_add_tts_models_dialog(self, self._settings_store)
        if not downloaded:
            return
        self._settings = self._settings_store.load()
        populate_tts_model_combo(self.bar.model_combo, self._settings)
        self.bar.model_combo.select_preferred([self._settings.tts_model])
        self._rendered = []
        self._player.stop()
        self._refresh_bar()


def bind_transcript_playback_follow(controller: TranscriptTtsController, view) -> None:
    """Highlight and scroll the spoken turn as TTS advances."""
    highlight = getattr(view, "set_playback_time", None)
    clear = getattr(view, "clear_playback", None)
    if callable(highlight):
        controller.segment_started.connect(highlight)
        if callable(clear):
            controller.playback_stopped.connect(clear)
        return
    controller.segment_started.connect(view.scroll_to_time)
