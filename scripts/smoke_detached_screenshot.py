"""Render the detached transcript window and its placeholder tab offscreen."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from queue import Queue

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication

from speaker_transcriber.config import SettingsStore
from speaker_transcriber.ui.main_window import MainWindow
from speaker_transcriber.ui.theme import apply_application_theme

from smoke_detachable_tabs import sample_result


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    application = QApplication(sys.argv[:1])
    apply_application_theme(application)

    with tempfile.TemporaryDirectory() as directory:
        window = MainWindow(SettingsStore(Path(directory)), Queue())
        window.resize(1280, 720)
        window.show()
        application.processEvents()

        window.result = sample_result()
        window.transcript_panel.set_result(window.result)
        window._populate_speaker_table()
        application.processEvents()

        window.tabs.detach("transcript")
        application.processEvents()

        window.grab().save(str(target / "detached_main.png"))
        window.transcript_panel.window().grab().save(str(target / "detached_float.png"))

        window.tabs.dock_all()
        if window.ollama_model_worker is not None:
            window.ollama_model_worker.wait(10000)
        window.close()
        application.processEvents()
        window.deleteLater()
        application.processEvents()

    print(f"wrote screenshots to {target.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
