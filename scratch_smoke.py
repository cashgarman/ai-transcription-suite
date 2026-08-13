import pathlib
import queue
import tempfile

from PySide6.QtWidgets import QApplication

from speaker_transcriber.config import SettingsStore
from speaker_transcriber.ui.main_window import MainWindow
from speaker_transcriber.ui.oom_recovery_dialog import REDUCE_CTX, OomRecoveryChoice

print("imports ok", flush=True)
app = QApplication([])
print("app ok", flush=True)
store = SettingsStore(pathlib.Path(tempfile.mkdtemp()))
print("store ok", flush=True)
window = MainWindow(store, queue.Queue())
print("window ok", flush=True)
print(
    "slots:",
    all(
        hasattr(window, name)
        for name in (
            "_on_notes_out_of_memory",
            "_saved_oom_choice",
            "_apply_oom_choice",
            "_summary_cancelled",
            "_pdf_export_cancelled",
        )
    ),
    flush=True,
)
print("ctx before:", window._current_ollama_num_ctx(), flush=True)
window._apply_oom_choice(
    OomRecoveryChoice(action=REDUCE_CTX, num_ctx=4096, always=True)
)
print(
    "ctx after:",
    window._current_ollama_num_ctx(),
    "settings:",
    window.settings.ollama_num_ctx,
    "policy:",
    repr(window.settings.ollama_oom_policy),
    flush=True,
)
saved = store.load()
print("persisted:", saved.ollama_num_ctx, repr(saved.ollama_oom_policy), flush=True)
print("SMOKE OK", flush=True)
