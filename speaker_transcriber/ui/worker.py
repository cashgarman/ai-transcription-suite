from __future__ import annotations

import logging
import os
import threading

from PySide6.QtCore import QThread, Signal

from speaker_transcriber.errors import ProcessingCancelled
from speaker_transcriber.models.summarization import SummarizationProgress
from speaker_transcriber.config import DEFAULT_OLLAMA_NUM_CTX
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

    def __init__(
        self,
        text: str,
        model_name: str,
        num_ctx: int = DEFAULT_OLLAMA_NUM_CTX,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.text = text
        self.model_name = model_name
        self.num_ctx = num_ctx

    def run(self) -> None:
        try:
            from speaker_transcriber.models.summarization import RequirementsSummarizer

            summarizer = RequirementsSummarizer(self.model_name, num_ctx=self.num_ctx)

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


class PdfExportWorker(QThread):
    progress = Signal(object)
    chunk = Signal(str)
    section_break = Signal()
    summary_ready = Signal(str)
    completed = Signal(str)
    failed = Signal(str)

    SUMMARIZE_END = 0.70
    FORMAT_END = 0.85

    def __init__(
        self,
        destination: str,
        transcript_text: str,
        existing_markdown: str = "",
        model_name: str = "",
        num_ctx: int = DEFAULT_OLLAMA_NUM_CTX,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.destination = destination
        self.transcript_text = transcript_text
        self.existing_markdown = existing_markdown
        self.model_name = model_name
        self.num_ctx = num_ctx

    def run(self) -> None:
        try:
            from pathlib import Path

            from speaker_transcriber.export.meeting_document import (
                parse_meeting_markdown,
            )
            from speaker_transcriber.export.pdf_exporter import export_meeting_pdf
            from speaker_transcriber.models.summarization import (
                RequirementsSummarizer,
                SummarizationProgress,
            )

            def emit_progress(fraction: float, message: str) -> None:
                self.progress.emit(
                    SummarizationProgress(min(max(fraction, 0.0), 1.0), message)
                )

            markdown = self.existing_markdown.strip()
            stream_chunks = not bool(markdown)
            summarizer = None

            if not markdown:
                if not self.model_name:
                    raise RuntimeError(
                        "Select an available Ollama model before exporting a PDF "
                        "without an existing summary."
                    )
                emit_progress(0.0, "Summarizing for PDF…")
                summarizer = RequirementsSummarizer(
                    self.model_name,
                    num_ctx=self.num_ctx,
                )

                def on_summarize_progress(fraction: float, message: str) -> None:
                    emit_progress(fraction * self.SUMMARIZE_END, message)

                def on_chunk(text: str) -> None:
                    if stream_chunks:
                        self.chunk.emit(text)

                def on_section_break() -> None:
                    if stream_chunks:
                        self.section_break.emit()

                markdown = summarizer.summarize(
                    self.transcript_text,
                    on_progress=on_summarize_progress,
                    on_chunk=on_chunk,
                    on_section_break=on_section_break,
                )
            else:
                emit_progress(0.05, "Parsing meeting notes…")

            document = parse_meeting_markdown(markdown)
            if document.needs_format_pass():
                if not self.model_name:
                    raise RuntimeError(
                        "The meeting notes need formatting. Select an Ollama model "
                        "and try again."
                    )
                if summarizer is None:
                    summarizer = RequirementsSummarizer(
                        self.model_name,
                        num_ctx=self.num_ctx,
                    )
                emit_progress(self.SUMMARIZE_END, "Formatting meeting notes…")

                def on_format_progress(fraction: float, message: str) -> None:
                    span = self.FORMAT_END - self.SUMMARIZE_END
                    emit_progress(self.SUMMARIZE_END + fraction * span, message)

                markdown = summarizer.format_meeting_notes(
                    markdown,
                    on_progress=on_format_progress,
                )
                document = parse_meeting_markdown(markdown)

            self.summary_ready.emit(markdown)
            emit_progress(self.FORMAT_END, "Writing PDF…")
            export_meeting_pdf(document, Path(self.destination))
            emit_progress(1.0, "PDF export complete")
            self.completed.emit(self.destination)
        except Exception as exc:
            LOGGER.exception("PDF export worker failed")
            self.failed.emit(str(exc))
