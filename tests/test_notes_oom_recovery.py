import threading
from types import SimpleNamespace

import pytest

from speaker_transcriber.config import AppSettings
from speaker_transcriber.ui.oom_recovery_dialog import (
    REDUCE_CTX,
    SMALLER_MODEL,
    STOP,
    OomRecoveryChoice,
    OomRecoveryRequest,
)
from speaker_transcriber.ui.worker import NotesMemoryRecoveryMixin


class FakeSignal:
    def __init__(self, responder=None) -> None:
        self.payloads: list[object] = []
        self.responder = responder

    def emit(self, payload: object) -> None:
        self.payloads.append(payload)
        if self.responder is not None:
            self.responder(payload)


class FakeWorker(NotesMemoryRecoveryMixin):
    def __init__(self, model_name: str, num_ctx: int, responder=None) -> None:
        self.model_name = model_name
        self.num_ctx = num_ctx
        self.oom_detected = FakeSignal(responder)
        self._init_recovery()

    def _smaller_model(self) -> str:
        return "gemma3:1b"


def test_recovery_lowers_context_and_retries() -> None:
    worker = FakeWorker("qwen3.5:9b", 16384)
    worker.oom_detected.responder = lambda request: worker.provide_recovery(
        OomRecoveryChoice(action=REDUCE_CTX, num_ctx=request.reduced_num_ctx)
    )
    assert worker._apply_recovery(RuntimeError("out of memory")) is True
    assert worker.num_ctx == 8192
    assert worker.model_name == "qwen3.5:9b"

    request = worker.oom_detected.payloads[0]
    assert isinstance(request, OomRecoveryRequest)
    assert request.num_ctx == 16384
    assert request.reduced_num_ctx == 8192
    assert request.smaller_model == "gemma3:1b"


def test_recovery_switches_model_and_retries() -> None:
    worker = FakeWorker("qwen3.5:9b", 8192)
    worker.oom_detected.responder = lambda request: worker.provide_recovery(
        OomRecoveryChoice(action=SMALLER_MODEL, model_name=request.smaller_model)
    )
    assert worker._apply_recovery(RuntimeError("out of memory")) is True
    assert worker.model_name == "gemma3:1b"
    assert worker.num_ctx == 8192


def test_recovery_stop_does_not_retry() -> None:
    worker = FakeWorker("qwen3.5:9b", 8192)
    worker.oom_detected.responder = lambda _request: worker.provide_recovery(
        OomRecoveryChoice(action=STOP)
    )
    assert worker._apply_recovery(RuntimeError("out of memory")) is False


def test_recovery_waits_for_the_ui_thread() -> None:
    worker = FakeWorker("qwen3.5:9b", 16384)
    answered = threading.Event()

    def answer_later(_request: object) -> None:
        def respond() -> None:
            answered.set()
            worker.provide_recovery(OomRecoveryChoice(action=REDUCE_CTX, num_ctx=4096))

        threading.Timer(0.05, respond).start()

    worker.oom_detected.responder = answer_later
    assert worker._apply_recovery(RuntimeError("out of memory")) is True
    assert answered.is_set()
    assert worker.num_ctx == 4096


def test_smallest_context_offers_no_reduction() -> None:
    worker = FakeWorker("qwen3.5:9b", 4096)
    worker.oom_detected.responder = lambda _request: worker.provide_recovery(
        OomRecoveryChoice(action=STOP)
    )
    worker._apply_recovery(RuntimeError("out of memory"))
    assert worker.oom_detected.payloads[0].reduced_num_ctx is None


def test_summarization_worker_retries_after_recovery(monkeypatch) -> None:
    """The worker restarts notes with the settings the user picked."""
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication

    import speaker_transcriber.models.summarization as summarization
    from speaker_transcriber.ui.worker import SummarizationWorker

    app = QApplication.instance() or QApplication([])
    attempts: list[tuple[str, int]] = []

    class FlakySummarizer:
        def __init__(self, model_name: str, *, num_ctx: int) -> None:
            attempts.append((model_name, num_ctx))
            self.num_ctx = num_ctx

        def summarize(self, text: str, **_kwargs) -> str:
            if len(attempts) == 1:
                raise summarization.OllamaOutOfMemoryError("out of memory")
            return f"# Notes\n\n{text}"

    monkeypatch.setattr(summarization, "RequirementsSummarizer", FlakySummarizer)

    worker = SummarizationWorker("Alex talked about the grid.", "qwen3.5:9b", 16384)
    monkeypatch.setattr(worker, "_smaller_model", lambda: "")
    completed: list[str] = []
    stopped: list[bool] = []
    worker.completed.connect(completed.append)
    worker.cancelled.connect(lambda: stopped.append(True))
    worker.oom_detected.connect(
        lambda request: worker.provide_recovery(
            OomRecoveryChoice(action=REDUCE_CTX, num_ctx=request.reduced_num_ctx)
        )
    )

    worker.run()
    app.processEvents()

    assert attempts == [("qwen3.5:9b", 16384), ("qwen3.5:9b", 8192)]
    assert completed and completed[0].startswith("# Notes")
    assert stopped == []


def test_summarization_worker_stops_when_asked(monkeypatch) -> None:
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication

    import speaker_transcriber.models.summarization as summarization
    from speaker_transcriber.ui.worker import SummarizationWorker

    app = QApplication.instance() or QApplication([])

    class AlwaysOom:
        def __init__(self, model_name: str, *, num_ctx: int) -> None:
            self.num_ctx = num_ctx

        def summarize(self, text: str, **_kwargs) -> str:
            raise summarization.OllamaOutOfMemoryError("out of memory")

    monkeypatch.setattr(summarization, "RequirementsSummarizer", AlwaysOom)

    worker = SummarizationWorker("Alex talked about the grid.", "qwen3.5:9b", 8192)
    monkeypatch.setattr(worker, "_smaller_model", lambda: "")
    stopped: list[bool] = []
    failed: list[str] = []
    worker.cancelled.connect(lambda: stopped.append(True))
    worker.failed.connect(failed.append)
    worker.oom_detected.connect(
        lambda _request: worker.provide_recovery(OomRecoveryChoice(action=STOP))
    )

    worker.run()
    app.processEvents()

    assert stopped == [True]
    assert failed == []


@pytest.mark.parametrize(
    ("policy", "request_kwargs", "expected"),
    [
        (
            "reduce_ctx",
            {"reduced_num_ctx": 8192, "smaller_model": ""},
            REDUCE_CTX,
        ),
        (
            "smaller_model",
            {"reduced_num_ctx": None, "smaller_model": "gemma3:1b"},
            SMALLER_MODEL,
        ),
        ("reduce_ctx", {"reduced_num_ctx": None, "smaller_model": ""}, None),
        ("smaller_model", {"reduced_num_ctx": 8192, "smaller_model": ""}, None),
        ("", {"reduced_num_ctx": 8192, "smaller_model": "gemma3:1b"}, None),
    ],
)
def test_saved_policy_is_applied_only_when_usable(
    policy: str,
    request_kwargs: dict,
    expected: str | None,
) -> None:
    """A remembered option is reused, but never when it cannot run."""
    from speaker_transcriber.ui.main_window import MainWindow

    settings = AppSettings(ollama_oom_policy=policy)
    window = SimpleNamespace(settings=settings)
    request = OomRecoveryRequest(model_name="qwen3.5:9b", num_ctx=16384, **request_kwargs)
    choice = MainWindow._saved_oom_choice(window, request)
    if expected is None:
        assert choice is None
    else:
        assert choice is not None
        assert choice.action == expected
        assert choice.always is True
