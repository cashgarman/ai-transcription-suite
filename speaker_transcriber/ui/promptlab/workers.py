"""One background thread for every Prompt Lab job.

Ollama serializes on the GPU, so running lab jobs concurrently would only make
them contend for the same memory and turn one out-of-memory failure into
several. Everything therefore goes through a single FIFO queue on one thread:
generation, summarization, judging, and optimization all wait their turn, and
the UI shows how deep the queue is.

Out-of-memory handling mirrors the main window's: the thread pauses, the UI asks
the user how to continue, and the same job is retried with a smaller context or
a smaller model rather than being lost.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QThread, Signal

from speaker_transcriber.errors import ProcessingCancelled
from speaker_transcriber.ui.promptlab._debug_log import agent_log
from speaker_transcriber.ui.oom_recovery_dialog import (
    OomRecoveryChoice,
    OomRecoveryRequest,
    REDUCE_CTX,
    SMALLER_MODEL,
    STOP,
)


LOGGER = logging.getLogger("speaker_transcriber.promptlab.workers")

KIND_GENERATE = "generate"
KIND_SUMMARIZE = "summarize"
KIND_JUDGE = "judge"
KIND_OPTIMIZE = "optimize"


@dataclass
class LabJob:
    """A unit of work the runner executes to completion before starting the next.

    `model_name` and `num_ctx` live on the job rather than being captured by the
    callable so out-of-memory recovery can lower them and retry the same job.
    """

    job_id: str
    kind: str
    label: str
    model_name: str
    num_ctx: int
    run: Callable[["JobContext"], Any]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class JobContext:
    job: LabJob
    cancel_event: threading.Event
    progress: Callable[[float, str], None]
    chunk: Callable[[str], None]

    @property
    def model_name(self) -> str:
        return self.job.model_name

    @property
    def num_ctx(self) -> int:
        return self.job.num_ctx

    def raise_if_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise ProcessingCancelled()


class LabJobRunner(QThread):
    """A worker thread draining a queue of `LabJob`s, one at a time."""

    job_started = Signal(object)
    job_progress = Signal(str, float, str)
    job_chunk = Signal(str, str)
    job_finished = Signal(str, object)
    job_failed = Signal(str, str)
    job_cancelled = Signal(str)
    queue_changed = Signal(int)
    idle = Signal()
    oom_detected = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._queue: queue.Queue[LabJob | None] = queue.Queue()
        self._pending: list[LabJob] = []
        self._pending_lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._stopping = False
        self._recovery_event = threading.Event()
        self._recovery_choice: OomRecoveryChoice | None = None
        self.current_job: LabJob | None = None

    # Queue management, called from the UI thread.

    def enqueue(self, job: LabJob) -> None:
        with self._pending_lock:
            self._pending.append(job)
            depth = len(self._pending)
        self._queue.put(job)
        self.queue_changed.emit(depth)

    def enqueue_all(self, jobs: list[LabJob]) -> None:
        for job in jobs:
            self.enqueue(job)

    @property
    def depth(self) -> int:
        with self._pending_lock:
            return len(self._pending)

    def pending_jobs(self) -> list[LabJob]:
        with self._pending_lock:
            return list(self._pending)

    def cancel_all(self) -> None:
        """Drop everything queued and cancel whatever is running."""
        with self._pending_lock:
            dropped = [job for job in self._pending if job is not self.current_job]
            self._pending = [job for job in self._pending if job is self.current_job]
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        for job in dropped:
            self.job_cancelled.emit(job.job_id)
        self._cancel_event.set()
        self.provide_recovery(OomRecoveryChoice(action=STOP))
        self.queue_changed.emit(self.depth)

    def stop(self) -> None:
        self._stopping = True
        self.cancel_all()
        self._queue.put(None)

    def provide_recovery(self, choice: OomRecoveryChoice) -> None:
        self._recovery_choice = choice
        self._recovery_event.set()

    # Thread body.

    def run(self) -> None:
        while True:
            job = self._queue.get()
            if job is None or self._stopping:
                break
            self.current_job = job
            self._cancel_event.clear()
            self.job_started.emit(job)
            self._execute(job)
            with self._pending_lock:
                if job in self._pending:
                    self._pending.remove(job)
                depth = len(self._pending)
            self.current_job = None
            self.queue_changed.emit(depth)
            if depth == 0:
                self.idle.emit()

    def _execute(self, job: LabJob) -> None:
        from speaker_transcriber.models.summarization import OllamaOutOfMemoryError

        context = JobContext(
            job=job,
            cancel_event=self._cancel_event,
            progress=lambda fraction, message: self.job_progress.emit(
                job.job_id, fraction, message
            ),
            chunk=lambda text: self.job_chunk.emit(job.job_id, text),
        )
        while True:
            try:
                if self._cancel_event.is_set():
                    self.job_cancelled.emit(job.job_id)
                    return
                result = job.run(context)
                # #region agent log
                agent_log(
                    "workers.py:_execute",
                    "about to emit job_finished",
                    {
                        "job_id": job.job_id,
                        "kind": job.kind,
                        "current_job_set": self.current_job is job,
                        "pending_has_job": job in self._pending,
                    },
                    "H1",
                )
                # #endregion
                self.job_finished.emit(job.job_id, result)
                return
            except ProcessingCancelled:
                self.job_cancelled.emit(job.job_id)
                return
            except OllamaOutOfMemoryError as exc:
                LOGGER.warning("Lab job %s ran out of GPU memory: %s", job.label, exc)
                if self._cancel_event.is_set() or not self._apply_recovery(job, exc):
                    self.job_cancelled.emit(job.job_id)
                    return
                continue
            except Exception as exc:
                LOGGER.exception("Lab job %s failed", job.label)
                self.job_failed.emit(job.job_id, str(exc))
                return

    def _apply_recovery(self, job: LabJob, error: Exception) -> bool:
        from speaker_transcriber.config import previous_ollama_num_ctx

        self._recovery_event.clear()
        self._recovery_choice = None
        self.oom_detected.emit(
            OomRecoveryRequest(
                model_name=job.model_name,
                num_ctx=job.num_ctx,
                message=str(error),
                reduced_num_ctx=previous_ollama_num_ctx(job.num_ctx),
                smaller_model=_smaller_model(job.model_name),
            )
        )
        self._recovery_event.wait()
        choice = self._recovery_choice
        if choice is None or choice.action == STOP:
            return False
        if choice.action == REDUCE_CTX and choice.num_ctx:
            LOGGER.info("Retrying %s at num_ctx %d", job.label, choice.num_ctx)
            job.num_ctx = int(choice.num_ctx)
        elif choice.action == SMALLER_MODEL and choice.model_name:
            LOGGER.info("Retrying %s with model %s", job.label, choice.model_name)
            job.model_name = str(choice.model_name)
        return True


def _smaller_model(model_name: str) -> str:
    from speaker_transcriber.models.summarization import RequirementsSummarizer

    try:
        models = RequirementsSummarizer.list_available_models()
    except Exception:
        LOGGER.debug("Could not list Ollama models for recovery", exc_info=True)
        return ""
    current = next((model for model in models if model.name == model_name), None)
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
