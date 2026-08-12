from __future__ import annotations

import sys
from dataclasses import dataclass
from queue import Queue
from typing import Any


@dataclass
class BootstrapResult:
    settings_store: Any
    log_queue: Queue
    main_window_type: type


def main() -> int:
    from PySide6.QtCore import QEventLoop, QThread, Qt, Signal
    from PySide6.QtWidgets import QApplication, QMessageBox

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    application = QApplication(sys.argv)
    application.setApplicationName("Summit")
    application.setOrganizationName("SpeakerTranscriber")

    from speaker_transcriber.ui.theme import apply_application_theme

    apply_application_theme(application)

    from speaker_transcriber.ui.splash import SplashScreen

    splash = SplashScreen()
    splash.show()
    application.processEvents()

    class BootstrapWorker(QThread):
        status = Signal(str, float)
        completed = Signal(object)
        failed = Signal(str)

        def run(self) -> None:
            try:
                self.status.emit("Configuring runtime…", 0.15)
                from speaker_transcriber.cuda_setup import configure_cuda_libraries
                from speaker_transcriber.huggingface_compat import (
                    patch_hf_hub_use_auth_token,
                )
                from speaker_transcriber.huggingface_setup import (
                    configure_huggingface_client,
                )
                from speaker_transcriber.pytorch_compat import (
                    patch_torch_load_weights_only,
                )
                from speaker_transcriber.speechbrain_compat import (
                    patch_speechbrain_lazy_modules,
                )

                configure_cuda_libraries()
                configure_huggingface_client()
                patch_hf_hub_use_auth_token()
                patch_torch_load_weights_only()
                patch_speechbrain_lazy_modules()

                self.status.emit("Preparing logging…", 0.45)
                from speaker_transcriber.config import SettingsStore
                from speaker_transcriber.logging_config import (
                    configure_logging,
                    log_system_information,
                )

                log_queue: Queue = Queue()
                logger = configure_logging(gui_queue=log_queue)
                log_system_information(logger)

                self.status.emit("Loading system prompts…", 0.6)
                from speaker_transcriber.prompts import load_prompts

                load_prompts()

                self.status.emit("Loading interface…", 0.75)
                from speaker_transcriber.ui.main_window import MainWindow

                self.completed.emit(
                    BootstrapResult(
                        settings_store=SettingsStore(),
                        log_queue=log_queue,
                        main_window_type=MainWindow,
                    )
                )
            except Exception as exc:
                self.failed.emit(str(exc))

    loop = QEventLoop()
    bootstrap = BootstrapWorker()
    state: dict[str, Any] = {"result": None, "error": None}

    def on_completed(result: object) -> None:
        state["result"] = result
        loop.quit()

    def on_failed(message: str) -> None:
        state["error"] = message
        loop.quit()

    bootstrap.status.connect(splash.set_status)
    bootstrap.completed.connect(on_completed)
    bootstrap.failed.connect(on_failed)
    bootstrap.finished.connect(loop.quit)
    bootstrap.start()
    loop.exec()
    bootstrap.wait(5000)

    if state["error"] is not None:
        splash.close()
        QMessageBox.critical(
            None,
            "Startup failed",
            f"Summit could not finish starting:\n\n{state['error']}",
        )
        return 1

    result = state["result"]
    if not isinstance(result, BootstrapResult):
        splash.close()
        QMessageBox.critical(
            None,
            "Startup failed",
            "Summit could not finish starting.",
        )
        return 1

    splash.set_status("Opening window…", 0.9)
    window = result.main_window_type(result.settings_store, result.log_queue)
    splash.set_status("Ready", 1.0)
    splash.finish(window)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
