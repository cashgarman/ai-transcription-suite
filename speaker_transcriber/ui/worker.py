from __future__ import annotations

import logging
import os
import threading

from PySide6.QtCore import QThread, Signal

from speaker_transcriber.errors import NoSpeechError, ProcessingCancelled, TrialLimitError
from speaker_transcriber.models.summarization import SummarizationProgress
from speaker_transcriber.pipeline.processor import TranscriptionProcessor
from speaker_transcriber.pipeline.types import ProcessingOptions, ProgressUpdate
from speaker_transcriber.prompts import DEFAULT_STYLE, get_style, normalize_style
from speaker_transcriber.ui.oom_recovery_dialog import (
    OomRecoveryChoice,
    OomRecoveryRequest,
    REDUCE_CTX,
    SMALLER_MODEL,
    STOP,
)


LOGGER = logging.getLogger("speaker_transcriber.worker")


class NotesMemoryRecoveryMixin:
    """Pauses a notes worker on GPU OOM until the UI supplies a recovery choice."""

    oom_detected = None  # provided by the QThread subclass as a Signal

    def _init_recovery(self) -> None:
        self._recovery_event = threading.Event()
        self._recovery_choice: OomRecoveryChoice | None = None

    def provide_recovery(self, choice: OomRecoveryChoice) -> None:
        """Called from the UI thread once the user has chosen how to continue."""
        self._recovery_choice = choice
        self._recovery_event.set()

    def _apply_recovery(self, error: Exception) -> bool:
        """Ask the UI what to do. Returns True when the caller should retry."""
        from speaker_transcriber.config import previous_ollama_num_ctx

        self._recovery_event.clear()
        self._recovery_choice = None
        self.oom_detected.emit(
            OomRecoveryRequest(
                model_name=self.model_name,
                num_ctx=self.num_ctx,
                message=str(error),
                reduced_num_ctx=previous_ollama_num_ctx(self.num_ctx),
                smaller_model=self._smaller_model(),
            )
        )
        self._recovery_event.wait()
        choice = self._recovery_choice
        if choice is None or choice.action == STOP:
            return False
        if choice.action == REDUCE_CTX and choice.num_ctx:
            LOGGER.info(
                "Retrying notes with a smaller context window (%d to %d)",
                self.num_ctx,
                choice.num_ctx,
            )
            self.num_ctx = int(choice.num_ctx)
        elif choice.action == SMALLER_MODEL and choice.model_name:
            LOGGER.info(
                "Retrying notes with a smaller model (%s to %s)",
                self.model_name,
                choice.model_name,
            )
            self.model_name = str(choice.model_name)
        else:
            LOGGER.info("Retrying notes with unchanged settings")
        return True

    def _smaller_model(self) -> str:
        from speaker_transcriber.models.summarization import RequirementsSummarizer

        try:
            models = RequirementsSummarizer.list_available_models()
        except Exception:
            LOGGER.debug("Could not list Ollama models for recovery", exc_info=True)
            return ""
        current = next(
            (model for model in models if model.name == self.model_name),
            None,
        )
        if current is None or not current.size_bytes:
            return ""
        smaller = [
            model
            for model in models
            if model.size_bytes and model.size_bytes < current.size_bytes
        ]
        if not smaller:
            return ""
        return max(smaller, key=lambda model: model.size_bytes or 0).name


class ProcessingWorker(QThread):
    progress = Signal(object)
    completed = Signal(object)
    cancelled = Signal(object)
    failed = Signal(str)
    trial_blocked = Signal(object)

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
        except NoSpeechError as exc:
            LOGGER.warning("Transcription found no speech: %s", exc)
            self.failed.emit(str(exc))
        except TrialLimitError as exc:
            LOGGER.warning("Trial limit blocked transcription: %s", exc)
            self.trial_blocked.emit(exc)
        except Exception as exc:
            LOGGER.exception("Processing worker failed")
            self.failed.emit(str(exc))

    def _emit_progress(self, update: ProgressUpdate) -> None:
        self.progress.emit(update)


class CatalogListWorker(QThread):
    completed = Signal(list)
    failed = Signal(str)

    def __init__(self, provider, query: str = "", family: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.provider = provider
        self.query = query
        self.family = family

    def run(self) -> None:
        try:
            from speaker_transcriber.huggingface_setup import configure_huggingface_client

            configure_huggingface_client()
            if self.family:
                entries = self.provider.list_variants(self.family)
            else:
                entries = self.provider.list_models(self.query)
            self.completed.emit(list(entries or []))
        except Exception as exc:
            LOGGER.exception("Failed to list catalog models")
            self.failed.emit(str(exc))


class CatalogDownloadWorker(QThread):
    progress = Signal(object)
    model_finished = Signal(str)
    failed = Signal(str)
    completed = Signal()

    def __init__(self, provider, names: list[str], parent=None) -> None:
        super().__init__(parent)
        self.provider = provider
        self.names = list(names)
        self.cancel_event = threading.Event()

    def request_cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            from speaker_transcriber.huggingface_setup import configure_huggingface_client

            configure_huggingface_client()
            for name in self.names:
                if self.cancel_event.is_set():
                    break
                self.provider.download(name, self._emit_progress, self.cancel_event)
                if not self.cancel_event.is_set():
                    self.model_finished.emit(name)
            self.completed.emit()
        except InterruptedError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            LOGGER.exception("Catalog download failed")
            self.failed.emit(str(exc))

    def _emit_progress(self, update) -> None:
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


class SummarizationWorker(QThread, NotesMemoryRecoveryMixin):
    progress = Signal(object)
    chunk = Signal(str)
    section_break = Signal()
    completed = Signal(str)
    failed = Signal(str)
    cancelled = Signal()
    oom_detected = Signal(object)

    excluded_sections: tuple[str, ...] = ()
    omit_speaker_names: bool = False

    def __init__(
        self,
        text: str,
        model_name: str,
        num_ctx: int,
        style: str = DEFAULT_STYLE,
        parent=None,
        *,
        excluded_sections: tuple[str, ...] = (),
        omit_speaker_names: bool = False,
    ) -> None:
        super().__init__(parent)
        self.text = text
        self.model_name = model_name
        self.num_ctx = int(num_ctx)
        self.style = normalize_style(style)
        self.excluded_sections = tuple(excluded_sections)
        self.omit_speaker_names = bool(omit_speaker_names)
        self.cancel_event = threading.Event()
        self._init_recovery()

    def request_cancel(self) -> None:
        self.cancel_event.set()
        self.provide_recovery(OomRecoveryChoice(action=STOP))

    def run(self) -> None:
        from speaker_transcriber.models.summarization import (
            OllamaOutOfMemoryError,
            RequirementsSummarizer,
        )

        def on_progress(fraction: float, message: str) -> None:
            self.progress.emit(SummarizationProgress(fraction, message))

        def on_chunk(text: str) -> None:
            self.chunk.emit(text)

        def on_section_break() -> None:
            self.section_break.emit()

        while True:
            try:
                if self.cancel_event.is_set():
                    self.cancelled.emit()
                    return
                summarizer = RequirementsSummarizer(
                    self.model_name,
                    num_ctx=self.num_ctx,
                    style=self.style,
                    excluded_sections=self.excluded_sections,
                    omit_speaker_names=self.omit_speaker_names,
                    cancel_event=self.cancel_event,
                )
                summary = summarizer.summarize(
                    self.text,
                    on_progress=on_progress,
                    on_chunk=on_chunk,
                    on_section_break=on_section_break,
                )
                self.completed.emit(summary)
                return
            except ProcessingCancelled:
                self.cancelled.emit()
                return
            except OllamaOutOfMemoryError as exc:
                LOGGER.warning("Summarization ran out of GPU memory: %s", exc)
                if self.cancel_event.is_set() or not self._apply_recovery(exc):
                    self.cancelled.emit()
                    return
                self.section_break.emit()
                continue
            except Exception as exc:
                LOGGER.exception("Summarization worker failed")
                self.failed.emit(str(exc))
                return


class PdfExportWorker(QThread, NotesMemoryRecoveryMixin):
    progress = Signal(object)
    chunk = Signal(str)
    section_break = Signal()
    summary_ready = Signal(str)
    completed = Signal(str)
    failed = Signal(str)
    cancelled = Signal()
    oom_detected = Signal(object)

    SUMMARIZE_END = 0.70
    FORMAT_END = 0.85

    excluded_sections: tuple[str, ...] = ()
    omit_speaker_names: bool = False
    pdf_options: dict[str, bool] | None = None

    def __init__(
        self,
        destination: str,
        transcript_text: str,
        existing_markdown: str = "",
        model_name: str = "",
        num_ctx: int = 0,
        pdf_engine: str = "reportlab",
        pdf_theme: str = "light",
        style: str = DEFAULT_STYLE,
        parent=None,
        *,
        excluded_sections: tuple[str, ...] = (),
        omit_speaker_names: bool = False,
        pdf_options: dict[str, bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.destination = destination
        self.transcript_text = transcript_text
        self.existing_markdown = existing_markdown
        self.model_name = model_name
        self.num_ctx = int(num_ctx)
        self.pdf_engine = pdf_engine
        self.pdf_theme = pdf_theme
        self.style = normalize_style(style)
        self.excluded_sections = tuple(excluded_sections)
        self.omit_speaker_names = bool(omit_speaker_names)
        self.pdf_options = dict(pdf_options) if pdf_options else None
        self.cancel_event = threading.Event()
        self._init_recovery()

    def request_cancel(self) -> None:
        self.cancel_event.set()
        self.provide_recovery(OomRecoveryChoice(action=STOP))

    def run(self) -> None:
        from speaker_transcriber.models.summarization import OllamaOutOfMemoryError

        while True:
            try:
                if self.cancel_event.is_set():
                    self.cancelled.emit()
                    return
                self._export()
                return
            except ProcessingCancelled:
                self.cancelled.emit()
                return
            except OllamaOutOfMemoryError as exc:
                LOGGER.warning("PDF notes generation ran out of GPU memory: %s", exc)
                if self.cancel_event.is_set() or not self._apply_recovery(exc):
                    self.cancelled.emit()
                    return
                self.section_break.emit()
                continue
            except Exception as exc:
                LOGGER.exception("PDF export worker failed")
                self.failed.emit(str(exc))
                return

    def _export(self) -> None:
        from pathlib import Path

        from speaker_transcriber.export.meeting_document import (
            parse_meeting_markdown,
        )
        from speaker_transcriber.export.pdf_exporter import export_meeting_pdf
        from speaker_transcriber.models.section_filter import move_sections_to_end
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
            if self.num_ctx <= 0:
                raise RuntimeError(
                    "A Notes context length is required to write meeting notes."
                )
            emit_progress(0.0, "Summarizing for PDF…")
            summarizer = RequirementsSummarizer(
                self.model_name,
                num_ctx=self.num_ctx,
                style=self.style,
                excluded_sections=self.excluded_sections,
                omit_speaker_names=self.omit_speaker_names,
                cancel_event=self.cancel_event,
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

        style = get_style(self.style)
        # Summaries written before a trailing-section change keep working: the
        # relocation is deterministic and a no-op on already-ordered documents.
        markdown = move_sections_to_end(markdown, style.trailing_sections)
        document = parse_meeting_markdown(markdown)
        if style.is_meeting_family and document.needs_format_pass(
            require_action_table=style.requires_action_table(self.excluded_sections)
        ):
            if not self.model_name:
                raise RuntimeError(
                    "The meeting notes need formatting. Select an Ollama model "
                    "and try again."
                )
            if self.num_ctx <= 0:
                raise RuntimeError(
                    "A Notes context length is required to format meeting notes."
                )
            if summarizer is None:
                summarizer = RequirementsSummarizer(
                    self.model_name,
                    num_ctx=self.num_ctx,
                    style=self.style,
                    excluded_sections=self.excluded_sections,
                    omit_speaker_names=self.omit_speaker_names,
                    cancel_event=self.cancel_event,
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

        if self.cancel_event.is_set():
            raise ProcessingCancelled()
        self.summary_ready.emit(markdown)
        emit_progress(self.FORMAT_END, "Writing PDF…")
        export_meeting_pdf(
            document,
            Path(self.destination),
            engine=self.pdf_engine,
            theme=self.pdf_theme,
            style=self.style,
            options=self.pdf_options,
        )
        emit_progress(1.0, "PDF export complete")
        self.completed.emit(self.destination)
