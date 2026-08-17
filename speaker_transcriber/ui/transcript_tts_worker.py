from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from speaker_transcriber.audio.tts.factory import create_tts_backend
from speaker_transcriber.audio.tts.export import export_rendered_mp3
from speaker_transcriber.audio.tts.renderer import cache_fingerprint, render_transcript
from speaker_transcriber.audio.tts.types import RenderedSegment
from speaker_transcriber.audio.tts.voices import assign_voices, speakers_in_appearance_order
from speaker_transcriber.config import app_data_dir
from speaker_transcriber.errors import ProcessingCancelled, TtsError
from speaker_transcriber.models.tts_catalog import WINDOWS_TTS_MODEL
from speaker_transcriber.pipeline.types import TranscriptResult


LOGGER = logging.getLogger("speaker_transcriber.ui.tts")


def tts_cache_dir() -> Path:
    return app_data_dir() / "tts_cache"


class TranscriptTtsRenderWorker(QThread):
    progress = Signal(int, int, str)
    render_finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        result: TranscriptResult,
        parent=None,
        *,
        backend=None,
        cache_root: Path | None = None,
        tts_model: str = WINDOWS_TTS_MODEL,
        extra_tts_models: list[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self._result = result
        self._backend = backend
        self._cache_root = cache_root or tts_cache_dir()
        self._tts_model = tts_model
        self._extra_tts_models = list(extra_tts_models or [])
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        backend = self._backend or create_tts_backend(
            self._tts_model,
            extra_voice_ids=self._extra_tts_models,
        )
        owns_backend = self._backend is None
        try:
            voices = backend.list_voices()
            preferred = (
                self._tts_model
                if self._tts_model != WINDOWS_TTS_MODEL
                else None
            )
            voice_map = assign_voices(
                speakers_in_appearance_order(self._result),
                voices,
                genders=self._result.speaker_genders,
                preferred_voice=preferred,
            )
            fingerprint = cache_fingerprint(
                self._result,
                voice_map,
                engine=self._tts_model,
            )
            work_dir = self._cache_root / fingerprint
            segments = render_transcript(
                self._result,
                backend=backend,
                work_dir=work_dir,
                progress_cb=self._emit_progress,
                cancel_event=self._cancel,
                voice_map=voice_map,
            )
            if self._cancel.is_set():
                self.cancelled.emit()
                return
            self.render_finished.emit(segments)
        except ProcessingCancelled:
            self.cancelled.emit()
        except (TtsError, OSError) as exc:
            LOGGER.exception("TTS render failed")
            self.failed.emit(str(exc))
        except Exception as exc:
            LOGGER.exception("TTS render failed")
            self.failed.emit(str(exc))
        finally:
            if owns_backend:
                close = getattr(backend, "close", None)
                if callable(close):
                    close()

    def _emit_progress(self, current: int, total: int, message: str) -> None:
        self.progress.emit(current, total, message)


class TranscriptTtsExportWorker(QThread):
    export_finished = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        segments: list[RenderedSegment],
        destination: Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._segments = segments
        self._destination = Path(destination)
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            export_rendered_mp3(self._segments, self._destination, self._cancel)
            if self._cancel.is_set():
                self.cancelled.emit()
                return
            self.export_finished.emit(str(self._destination))
        except ProcessingCancelled:
            self.cancelled.emit()
        except Exception as exc:
            LOGGER.exception("TTS export failed")
            self.failed.emit(str(exc))
