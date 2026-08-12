from __future__ import annotations

import logging
import os
import threading

from PySide6.QtCore import QThread, Signal

from speaker_transcriber.errors import ProcessingCancelled
from speaker_transcriber.models.summarization import SummarizationProgress
from speaker_transcriber.pipeline.processor import TranscriptionProcessor
from speaker_transcriber.pipeline.types import ProcessingOptions, ProgressUpdate


LOGGER = logging.getLogger("speaker_transcriber.worker")


class ProcessingWorker(QThread):
    progress = Signal(object)
    completed = Signal(object)
    cancelled = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        sources: list[str],
        options: ProcessingOptions,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.sources = sources
        self.options = options
        self.cancel_event = threading.Event()

    def request_cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            from speaker_transcriber.cuda_setup import configure_cuda_libraries
            from speaker_transcriber.debug_log import agent_log
            from speaker_transcriber.huggingface_setup import configure_huggingface_client
            from speaker_transcriber.huggingface_compat import patch_hf_hub_use_auth_token
            from speaker_transcriber.pytorch_compat import patch_torch_load_weights_only
            from speaker_transcriber.speechbrain_compat import patch_speechbrain_lazy_modules

            configure_cuda_libraries()
            configure_huggingface_client()
            patch_hf_hub_use_auth_token()
            patch_torch_load_weights_only()
            patch_speechbrain_lazy_modules()
            agent_log(
                "worker.py:run",
                "worker thread started",
                {
                    "thread": threading.current_thread().name,
                    "path_contains_cudnn": "nvidia\\cudnn\\bin"
                    in os.environ.get("PATH", "").lower(),
                },
                "H5",
            )
            result = TranscriptionProcessor().run(
                self.sources,
                self.options,
                self.cancel_event,
                self._emit_progress,
            )
            self.completed.emit(result)
        except ProcessingCancelled as exc:
            self.cancelled.emit(exc.partial_result)
        except Exception as exc:
            LOGGER.exception("Processing worker failed")
            self.failed.emit(str(exc))

    def _emit_progress(self, update: ProgressUpdate) -> None:
        self.progress.emit(update)


class OllamaModelListWorker(QThread):
    completed = Signal(list)
    failed = Signal(str)

    def run(self) -> None:
        try:
            from speaker_transcriber.models.summarization import RequirementsSummarizer

            self.completed.emit(RequirementsSummarizer.list_available_models())
        except Exception as exc:
            LOGGER.exception("Failed to list Ollama models")
            self.failed.emit(str(exc))


class SummarizationWorker(QThread):
    progress = Signal(object)
    chunk = Signal(str)
    section_break = Signal()
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, text: str, model_name: str, parent=None) -> None:
        super().__init__(parent)
        self.text = text
        self.model_name = model_name

    def run(self) -> None:
        try:
            from speaker_transcriber.models.summarization import RequirementsSummarizer

            summarizer = RequirementsSummarizer(self.model_name)

            def on_progress(fraction: float, message: str) -> None:
                self.progress.emit(SummarizationProgress(fraction, message))

            def on_chunk(text: str) -> None:
                self.chunk.emit(text)

            def on_section_break() -> None:
                self.section_break.emit()

            summary = summarizer.summarize(
                self.text,
                on_progress=on_progress,
                on_chunk=on_chunk,
                on_section_break=on_section_break,
            )
            self.completed.emit(summary)
        except Exception as exc:
            LOGGER.exception("Summarization worker failed")
            self.failed.emit(str(exc))
