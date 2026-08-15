from PySide6.QtWidgets import QApplication

from speaker_transcriber.config import AppSettings, SettingsStore
from speaker_transcriber.ui.settings_dialog import SettingsDialog


def _application() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def test_settings_dialog_builds(tmp_path) -> None:
    _application()
    dialog = SettingsDialog(AppSettings(), SettingsStore(tmp_path))
    assert "Trial mode" in dialog.license_status.text()
    dialog.close()
