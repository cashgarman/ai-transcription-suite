from __future__ import annotations

import signal
import threading
import time
from queue import Queue

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from speaker_transcriber.config import SettingsStore
from speaker_transcriber.qt_interrupt import (
    INTERRUPT_EXIT_CODE,
    exec_with_interrupt_handling,
    install_interrupt_handling,
    interrupt_exit_code,
    is_interrupt_requested,
    request_interrupt,
    reset_interrupt_state,
)
from speaker_transcriber.qt_interrupt import _handle_interrupt
from speaker_transcriber.ui.main_window import MainWindow


def _application() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


@pytest.fixture
def application():
    app = _application()
    reset_interrupt_state(app)
    yield app
    reset_interrupt_state(app)


def test_request_interrupt_marks_the_application(application: QApplication) -> None:
    assert not is_interrupt_requested(application)
    request_interrupt(application)
    assert is_interrupt_requested(application)
    assert interrupt_exit_code(application, 0) == INTERRUPT_EXIT_CODE


def test_exec_returns_130_when_keyboardinterrupt_is_raised(
    application: QApplication,
) -> None:
    def boom() -> int:
        raise KeyboardInterrupt

    assert exec_with_interrupt_handling(boom, application) == INTERRUPT_EXIT_CODE
    assert is_interrupt_requested(application)


def test_exec_returns_130_when_already_interrupted(
    application: QApplication,
) -> None:
    request_interrupt(application)
    assert exec_with_interrupt_handling(lambda: 0, application) == INTERRUPT_EXIT_CODE


def test_exec_preserves_normal_exit_code(application: QApplication) -> None:
    assert exec_with_interrupt_handling(lambda: 0, application) == 0


def test_sigint_handler_requests_a_graceful_quit(application: QApplication) -> None:
    install_interrupt_handling(application)
    handler = signal.getsignal(signal.SIGINT)
    handler(signal.SIGINT, None)  # type: ignore[misc, operator]
    assert is_interrupt_requested(application)


def test_second_sigint_forces_process_exit(
    application: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    forced: list[int] = []
    monkeypatch.setattr(
        "speaker_transcriber.qt_interrupt.os._exit",
        lambda code: forced.append(code),
    )
    _handle_interrupt()
    _handle_interrupt()
    assert is_interrupt_requested(application)
    assert forced == [INTERRUPT_EXIT_CODE]


def test_close_skips_confirmations_after_interrupt(
    application: QApplication, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = MainWindow(SettingsStore(tmp_path), Queue())

    class FakeWorker:
        def __init__(self) -> None:
            self.cancelled = False

        def isRunning(self) -> bool:  # noqa: N802 - Qt naming
            return True

        def request_cancel(self) -> None:
            self.cancelled = True

        def wait(self, _milliseconds: int) -> bool:
            return True

    fake = FakeWorker()
    window.worker = fake  # type: ignore[assignment]
    questions: list[object] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: questions.append(args) or QMessageBox.StandardButton.No,
    )
    request_interrupt(application)
    window.gpu_stats_timer.stop()
    window.log_timer.stop()
    window.elapsed_timer.stop()
    if window.ollama_model_worker is not None:
        window.ollama_model_worker.wait(2000)
    window.close()
    assert questions == []
    assert fake.cancelled


def test_request_interrupt_from_background_thread_quits_on_main_thread(
    application: QApplication,
) -> None:
    install_interrupt_handling(application)
    quit_on_main: list[bool] = []
    original_quit = application.quit

    def tracked_quit() -> None:
        from PySide6.QtCore import QThread

        quit_on_main.append(QThread.currentThread() is application.thread())
        original_quit()

    application.quit = tracked_quit  # type: ignore[method-assign]

    thread = threading.Thread(target=lambda: request_interrupt(application), daemon=True)
    thread.start()
    thread.join(timeout=1.0)

    deadline = time.monotonic() + 2.0
    while not quit_on_main and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.01)

    assert quit_on_main == [True]
