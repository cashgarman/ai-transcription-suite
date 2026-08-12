from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from speaker_transcriber.export.common import display_speaker, speaker_color_map
from speaker_transcriber.pipeline.types import TranscriptResult
from speaker_transcriber.ui.theme import Theme


class TranscriptTimelineHeatmap(QWidget):
    segment_clicked = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(14)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self._result: TranscriptResult | None = None
        self._colors: dict[str, str] = {}
        self._selected_speaker: str | None = None
        self._scroll_fraction = 0.0
        self._viewport_fraction = 1.0
        self.setToolTip("Speaker activity along the transcript timeline")

    def set_result(self, result: TranscriptResult | None) -> None:
        self._result = result
        self._colors = speaker_color_map(result) if result else {}
        self.update()

    def set_selected_speaker(self, speaker_id: str | None) -> None:
        self._selected_speaker = speaker_id
        self.update()

    def set_scroll_state(self, scroll_fraction: float, viewport_fraction: float) -> None:
        self._scroll_fraction = max(0.0, min(scroll_fraction, 1.0))
        self._viewport_fraction = max(0.0, min(viewport_fraction, 1.0))
        self.update()

    def _duration(self) -> float:
        if self._result is None:
            return 0.0
        if self._result.duration_seconds > 0:
            return self._result.duration_seconds
        if not self._result.segments:
            return 0.0
        return max(segment.end for segment in self._result.segments)

    def _segment_rect(self, start: float, end: float, height: int) -> tuple[int, int, int, int]:
        duration = self._duration()
        if duration <= 0:
            return (0, 0, self.width(), 0)
        top = int((start / duration) * height)
        bottom = int((end / duration) * height)
        if bottom <= top:
            bottom = top + 2
        return (1, top, self.width() - 2, bottom - top)

    def _segment_at(self, y: int) -> tuple[float, float, str] | None:
        if self._result is None:
            return None
        duration = self._duration()
        if duration <= 0:
            return None
        seconds = (y / max(self.height(), 1)) * duration
        for segment in self._result.segments:
            if segment.start <= seconds <= segment.end:
                return (segment.start, segment.end, segment.speaker)
        return None

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        rect = self.rect()
        painter.fillRect(rect, QColor(Theme.SURFACE_SUNKEN))

        if self._result is None or not self._result.segments:
            painter.setPen(QColor(Theme.BORDER))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            return

        height = rect.height()
        for segment in self._result.segments:
            is_selected = segment.speaker == self._selected_speaker
            if self._selected_speaker is not None and not is_selected:
                continue
            color = QColor(self._colors.get(segment.speaker, "#B0BEC5"))
            if self._selected_speaker is None:
                color.setAlpha(140)
            painter.fillRect(*self._segment_rect(segment.start, segment.end, height), color)

        if self._selected_speaker is not None:
            painter.setPen(QPen(QColor(Theme.BORDER), 1))
            for segment in self._result.segments:
                if segment.speaker == self._selected_speaker:
                    continue
                dim = QColor(Theme.TEXT_MUTED)
                dim.setAlpha(40)
                painter.fillRect(*self._segment_rect(segment.start, segment.end, height), dim)

        viewport_height = max(int(height * self._viewport_fraction), 4)
        viewport_top = int(self._scroll_fraction * max(height - viewport_height, 0))
        painter.setPen(QPen(QColor(Theme.TEXT), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(0, viewport_top, rect.width() - 1, viewport_height)

        painter.setPen(QColor(Theme.BORDER))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.end()

    def mouseMoveEvent(self, event) -> None:
        if self._result is None:
            return
        hit = self._segment_at(event.position().toPoint().y())
        if hit is None:
            QToolTip.hideText()
            return
        start, end, speaker_id = hit
        name = display_speaker(self._result, speaker_id)
        QToolTip.showText(
            event.globalPosition().toPoint(),
            f"{name}\n{self._format_range(start, end)}",
            self,
        )

    def mousePressEvent(self, event) -> None:
        if self._result is None:
            return
        hit = self._segment_at(event.position().toPoint().y())
        if hit is None:
            return
        self.segment_clicked.emit(hit[0])

    @staticmethod
    def _format_range(start: float, end: float) -> str:
        return f"{start:0.1f}s – {end:0.1f}s"
