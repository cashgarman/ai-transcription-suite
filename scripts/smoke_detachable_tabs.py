"""Headless check for detachable tabs, editable panels, and speaker sync."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from queue import Queue

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication

from speaker_transcriber.config import SettingsStore
from speaker_transcriber.pipeline.types import TranscriptResult, TranscriptSegment
from speaker_transcriber.ui.main_window import MainWindow
from speaker_transcriber.ui.theme import apply_application_theme


def sample_result() -> TranscriptResult:
    return TranscriptResult(
        source_file="sample.wav",
        language="en",
        duration_seconds=12.0,
        speakers={"SPEAKER_00": "Speaker 1", "SPEAKER_01": "Speaker 2"},
        segments=[
            TranscriptSegment(0.0, 4.0, "SPEAKER_00", "First speaker line."),
            TranscriptSegment(4.0, 8.0, "SPEAKER_01", "Second speaker line."),
            TranscriptSegment(8.0, 12.0, "SPEAKER_00", "Back to the first."),
        ],
    )


def main() -> int:
    application = QApplication(sys.argv)
    apply_application_theme(application)

    with tempfile.TemporaryDirectory() as directory:
        window = MainWindow(SettingsStore(Path(directory)), Queue())
        window.show()
        application.processEvents()

        window.result = sample_result()
        window.transcript_panel.set_result(window.result)
        window._populate_speaker_table()
        window.summary_view.setPlainText("summary text")
        application.processEvents()

        assert not window.transcript_panel.transcript_view.isReadOnly()
        assert not window.summary_view.isReadOnly()

        window.tabs.detach("transcript")
        window.tabs.detach("summary")
        application.processEvents()
        assert window.transcript_panel.window() is not window
        assert window.summary_view.window() is not window
        assert window.tabs.count() == 2

        window.result.speakers["SPEAKER_00"] = "Renamed Person"
        window.transcript_panel.set_result(window.result)
        window.transcript_panel.highlight_speaker("SPEAKER_00")
        application.processEvents()
        text = window.transcript_panel.transcript_view.toPlainText()
        assert "Renamed Person" in text, text

        window.result.remove_speaker("SPEAKER_01")
        window.transcript_panel.set_result(window.result)
        window._populate_speaker_table()
        application.processEvents()
        text = window.transcript_panel.transcript_view.toPlainText()
        assert "Second speaker line." not in text, text

        window.tabs.ensure_visible(window.summary_view)
        application.processEvents()

        window.tabs.dock("transcript")
        window.tabs.dock("summary")
        application.processEvents()
        assert window.transcript_panel.window() is window
        assert window.summary_view.window() is window
        assert window.tabs.count() == 2
        assert "Renamed Person" in window.transcript_panel.transcript_view.toPlainText()
        assert window.summary_view.toPlainText() == "summary text"

        window.tabs.detach("transcript")
        application.processEvents()
        window.tabs.dock_all()
        application.processEvents()
        assert window.transcript_panel.window() is window

        if window.ollama_model_worker is not None:
            window.ollama_model_worker.wait(10000)
        window.close()
        application.processEvents()
        window.deleteLater()
        application.processEvents()

    print("smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
