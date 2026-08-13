import queue
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from speaker_transcriber.config import SettingsStore
from speaker_transcriber.ui.main_window import MainWindow

app = QApplication([])
tmp = Path(tempfile.mkdtemp())
store = SettingsStore(tmp)
window = MainWindow(store, queue.Queue())
combo = window.summary_style_combo
print("styles in combo:", combo.count())
print("current:", window._current_summary_style())
combo.setCurrentIndex(2)
print("after change:", window._current_summary_style(), store.load().summary_style)
print("button text:", window.summarize_button.text())
