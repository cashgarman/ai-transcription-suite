from PySide6.QtWidgets import QApplication, QWidget

from speaker_transcriber.ui.notification import NotificationBanner


def _application() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def test_notification_banner_shows_message() -> None:
    _application()
    host = QWidget()
    host.resize(640, 400)
    banner = NotificationBanner(host)
    banner.show_message("Transcription complete", kind="success", duration_ms=800)
    assert banner._label.text() == "Transcription complete"
    assert banner.property("kind") == "success"
    banner.show_message("Loaded cached transcript", kind="info", duration_ms=800)
    assert len(banner._queue) == 1
