from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from speaker_transcriber.audio.ffmpeg import probe_media


LOGGER = logging.getLogger("speaker_transcriber.ui.duration_probe")


class MediaDurationProbeWorker(QThread):
    duration_ready = Signal(str, float)
    failed = Signal(str, str)

    def __init__(self, paths: list[str], parent=None) -> None:
        super().__init__(parent)
        self.paths = paths

    def run(self) -> None:
        for path_text in self.paths:
            path = Path(path_text)
            try:
                info = probe_media(path)
                self.duration_ready.emit(str(path.resolve()), info.duration_seconds)
            except Exception as exc:
                LOGGER.debug("Duration probe failed for %s: %s", path, exc)
                self.failed.emit(str(path.resolve()), str(exc))
