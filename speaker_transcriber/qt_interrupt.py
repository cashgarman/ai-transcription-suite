"""Map Ctrl+C / SIGINT to a graceful Qt shutdown.

Qt's C++ event loop does not run Python signal handlers on its own, and a
KeyboardInterrupt raised inside a Python paint or event-filter override is
caught by Shiboken, printed as a traceback, and then ignored.  Installing a
real SIGINT handler plus a short wakeup timer converts the interrupt into
``QApplication.quit()`` instead.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from collections.abc import Callable

from PySide6.QtCore import QEventLoop, QThread, QTimer
from PySide6.QtWidgets import QApplication


INTERRUPT_EXIT_CODE = 130
_TIMER_PROPERTY = "_summit_interrupt_timer"
_LOOP_PROPERTY = "_summit_active_event_loop"
_LOGGER = logging.getLogger("speaker_transcriber")

_interrupt_count = 0
_pending_interrupt = False
_windows_handler = None
_previous_signals: dict[int, object] = {}
_lock = threading.Lock()


def is_interrupt_requested(_application: QApplication | None = None) -> bool:
    return _pending_interrupt


def register_active_event_loop(
    application: QApplication, loop: QEventLoop | None
) -> None:
    application.setProperty(_LOOP_PROPERTY, loop)


def _quit_application(application: QApplication) -> None:
    loop = application.property(_LOOP_PROPERTY)
    if isinstance(loop, QEventLoop):
        loop.quit()
    for widget in application.topLevelWidgets():
        widget.close()
    application.quit()


def _schedule_application_quit(application: QApplication) -> None:
    if QThread.currentThread() is application.thread():
        _quit_application(application)
    else:
        QTimer.singleShot(0, application, lambda: _quit_application(application))


def request_interrupt(application: QApplication | None = None) -> None:
    """Ask the Qt event loop to leave; safe to call more than once."""
    global _pending_interrupt
    with _lock:
        already = _pending_interrupt
        _pending_interrupt = True
    app = application or QApplication.instance()
    if app is not None:
        _schedule_application_quit(app)
    if already:
        return
    message = "Interrupted; shutting down."
    if _LOGGER.handlers:
        _LOGGER.info(message)
    else:
        print(message, file=sys.stderr)


def interrupt_exit_code(application: QApplication | None, exec_code: int) -> int:
    if is_interrupt_requested(application):
        return INTERRUPT_EXIT_CODE
    return int(exec_code or 0)


def exec_with_interrupt_handling(
    exec_fn: Callable[[], int],
    application: QApplication,
) -> int:
    try:
        code = exec_fn()
    except KeyboardInterrupt:
        request_interrupt(application)
        return INTERRUPT_EXIT_CODE
    return interrupt_exit_code(application, code)


def install_interrupt_handling(application: QApplication) -> None:
    """Install SIGINT handling and a wakeup timer on ``application``."""
    _install_signal_handlers()
    _install_windows_console_handler()
    if not application.property(_TIMER_PROPERTY):
        timer = QTimer(application)
        timer.setObjectName("summit-interrupt-wakeup")
        timer.setInterval(200)
        timer.timeout.connect(lambda: None)
        timer.start()
        application.setProperty(_TIMER_PROPERTY, True)
    if _pending_interrupt:
        request_interrupt(application)


def reset_interrupt_state(application: QApplication | None = None) -> None:
    """Restore signal handlers and flags. Used by tests after installing handling."""
    global _interrupt_count, _pending_interrupt, _windows_handler
    with _lock:
        _interrupt_count = 0
        _pending_interrupt = False
    for sig, handler in _previous_signals.items():
        try:
            signal.signal(sig, handler)  # type: ignore[arg-type]
        except (ValueError, OSError):
            pass
    _previous_signals.clear()
    if _windows_handler is not None and sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleCtrlHandler(_windows_handler, False)
        except OSError:
            pass
        _windows_handler = None
    app = application or QApplication.instance()
    if app is None:
        return
    timer = app.findChild(QTimer, "summit-interrupt-wakeup")
    if timer is not None:
        timer.stop()
        timer.deleteLater()
    app.setProperty(_TIMER_PROPERTY, False)


def _handle_interrupt(*_args) -> None:
    global _interrupt_count
    with _lock:
        _interrupt_count += 1
        count = _interrupt_count
    if count >= 2:
        if _LOGGER.handlers:
            _LOGGER.warning("Second interrupt received; exiting immediately.")
        else:
            print("Second interrupt received; exiting immediately.", file=sys.stderr)
        os._exit(INTERRUPT_EXIT_CODE)
    request_interrupt()


def _remember_signal(sig: int) -> None:
    if sig not in _previous_signals:
        _previous_signals[sig] = signal.getsignal(sig)


def _install_signal_handlers() -> None:
    _remember_signal(signal.SIGINT)
    signal.signal(signal.SIGINT, _handle_interrupt)
    sigbreak = getattr(signal, "SIGBREAK", None)
    if sigbreak is not None:
        try:
            _remember_signal(sigbreak)
            signal.signal(sigbreak, _handle_interrupt)
        except (ValueError, OSError):
            pass
    if hasattr(signal, "SIGTERM"):
        try:
            _remember_signal(signal.SIGTERM)
            signal.signal(signal.SIGTERM, _handle_interrupt)
        except (ValueError, OSError):
            pass


def _install_windows_console_handler() -> bool:
    global _windows_handler
    if sys.platform != "win32" or _windows_handler is not None:
        return _windows_handler is not None
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return False

    handler_routine = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

    def _handler(ctrl_type: int) -> bool:
        if ctrl_type in (0, 1, 2):  # C, BREAK, CLOSE
            _handle_interrupt()
            return True
        return False

    _windows_handler = handler_routine(_handler)
    return bool(ctypes.windll.kernel32.SetConsoleCtrlHandler(_windows_handler, True))
