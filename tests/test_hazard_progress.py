from queue import Queue

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from speaker_transcriber.config import SettingsStore
from speaker_transcriber.pipeline.types import ProgressUpdate
from speaker_transcriber.ui.hazard_progress import HazardProgressBar
from speaker_transcriber.ui.main_window import MainWindow


def _application() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def test_hazard_progress_bar_tracks_value_and_animation() -> None:
    _application()
    bar = HazardProgressBar(bar_height=28, autostart=False)
    bar.setRange(0, 1000)
    assert bar.value() == 0
    assert not bar.is_animating()

    bar.start()
    bar.setValue(400)
    assert bar.value() == 400
    assert bar.is_animating()

    bar.setValue(2000)
    assert bar.value() == 1000
    bar.stop()
    assert not bar.is_animating()


def test_main_window_job_bar_is_animated_and_uncovered(tmp_path) -> None:
    _application()
    window = MainWindow(SettingsStore(tmp_path), Queue())
    assert isinstance(window.progress_bar, HazardProgressBar)
    assert window.progress_overlay.testAttribute(
        Qt.WidgetAttribute.WA_TranslucentBackground
    )
    assert not window.progress_bar.is_animating()

    window._on_progress(
        ProgressUpdate(
            stage="transcribing",
            progress=0.32,
            message="Transcribing speech",
            elapsed_seconds=4.0,
            stage_fraction=0.48,
        )
    )
    assert window.progress_bar.value() == 320
    assert window.progress_bar.is_animating()
    assert window.stage_label.text() == "Transcribing speech"
    assert window.stage_percent_label.text() == "48%"

    window._set_busy(False)
    assert not window.progress_bar.is_animating()
    window.gpu_stats_timer.stop()
    window.log_timer.stop()
    window.elapsed_timer.stop()
    if window.ollama_model_worker is not None:
        window.ollama_model_worker.wait(2000)
    window.close()
