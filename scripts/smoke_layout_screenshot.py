"""Render the main window offscreen so layout changes can be eyeballed."""

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
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "layout.png")
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
        window.stage_label.setText(
            "Complete — distil-large-v3, batch 4, alignment cuda, diarization cuda"
        )
        window.progress_bar.setValue(1000)
        application.processEvents()

        window.grab().save(str(output))

        if window.ollama_model_worker is not None:
            window.ollama_model_worker.wait(10000)
        window.close()
        application.processEvents()
        window.deleteLater()
        application.processEvents()

    print(f"wrote {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
