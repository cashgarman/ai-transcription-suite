from __future__ import annotations

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QWidget

from speaker_transcriber.pipeline.types import TranscriptResult
from speaker_transcriber.ui.busy_spinner import BusySpinnerOverlay
from speaker_transcriber.ui.transcript_heatmap import TranscriptTimelineHeatmap
from speaker_transcriber.ui.transcript_view import TranscriptView


class TranscriptPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.transcript_view = TranscriptView(self)
        self.heatmap = TranscriptTimelineHeatmap(self.transcript_view)
        self.heatmap.raise_()
        self._busy_overlay = BusySpinnerOverlay(self)

        self.transcript_view.verticalScrollBar().valueChanged.connect(
            self._update_heatmap_scroll
        )
        self.transcript_view.verticalScrollBar().rangeChanged.connect(
            lambda *_args: self._update_heatmap_scroll()
        )
        self.heatmap.segment_clicked.connect(self.transcript_view.scroll_to_time)
        self.transcript_view.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.transcript_view and event.type() == QEvent.Type.Resize:
            self._position_heatmap()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.transcript_view.setGeometry(self.rect())
        self._position_heatmap()
        self._busy_overlay.setGeometry(self.rect())
        if self._busy_overlay.isVisible():
            self._busy_overlay.raise_()

    def set_result(self, result: TranscriptResult | None) -> None:
        self.transcript_view.set_result(result)
        self.heatmap.set_result(result)
        self._update_heatmap_scroll()

    def highlight_speaker(self, speaker_id: str | None) -> None:
        self.transcript_view.highlight_speaker(speaker_id)
        self.heatmap.set_selected_speaker(speaker_id)

    def goto_adjacent_speaker_entry(self, speaker_id: str, delta: int) -> bool:
        return self.transcript_view.goto_adjacent_speaker_entry(speaker_id, delta)

    def goto_speaker_entry_edge(self, speaker_id: str, *, first: bool) -> bool:
        return self.transcript_view.goto_speaker_entry_edge(speaker_id, first=first)

    def set_busy(self, busy: bool) -> None:
        self._busy_overlay.setGeometry(self.rect())
        self._busy_overlay.set_busy(busy)
        if busy:
            self._busy_overlay.raise_()

    def clear(self) -> None:
        self.set_result(None)

    def _position_heatmap(self) -> None:
        scrollbar = self.transcript_view.verticalScrollBar()
        scrollbar_width = scrollbar.width() if scrollbar.isVisible() else 0
        heatmap_width = self.heatmap.width()
        x = self.transcript_view.width() - scrollbar_width - heatmap_width
        self.heatmap.setGeometry(
            max(x, 0),
            0,
            heatmap_width,
            self.transcript_view.height(),
        )
        self.heatmap.raise_()
        if self._busy_overlay.isVisible():
            self._busy_overlay.raise_()

    def _update_heatmap_scroll(self) -> None:
        scroll_bar = self.transcript_view.verticalScrollBar()
        maximum = scroll_bar.maximum()
        if maximum <= 0:
            self.heatmap.set_scroll_state(0.0, 1.0)
            return
        scroll_fraction = scroll_bar.value() / maximum
        viewport_fraction = scroll_bar.pageStep() / (maximum + scroll_bar.pageStep())
        self.heatmap.set_scroll_state(scroll_fraction, viewport_fraction)
        self._position_heatmap()
