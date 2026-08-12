from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from speaker_transcriber.pipeline.types import TranscriptResult
from speaker_transcriber.ui.busy_spinner import BusySpinnerOverlay
from speaker_transcriber.ui.text_search import TextSearchBar
from speaker_transcriber.ui.transcript_heatmap import TranscriptTimelineHeatmap
from speaker_transcriber.ui.transcript_view import TranscriptView


class TranscriptPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.search_bar = TextSearchBar("Search transcript…")
        layout.addWidget(self.search_bar)

        self._content_host = QWidget()
        self._content_host.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self._content_host, 1)

        self.transcript_view = TranscriptView(self._content_host)
        self.heatmap = TranscriptTimelineHeatmap(self.transcript_view)
        self.heatmap.raise_()
        self._busy_overlay = BusySpinnerOverlay(self._content_host)

        self.transcript_view.verticalScrollBar().valueChanged.connect(
            self._update_heatmap_scroll
        )
        self.transcript_view.verticalScrollBar().rangeChanged.connect(
            lambda *_args: self._update_heatmap_scroll()
        )
        self.heatmap.segment_clicked.connect(self.transcript_view.scroll_to_time)
        self.transcript_view.installEventFilter(self)
        self._content_host.installEventFilter(self)

        self.search_bar.query_changed.connect(self._on_search_query)
        self.search_bar.next_requested.connect(lambda: self._goto_search_match(1))
        self.search_bar.previous_requested.connect(lambda: self._goto_search_match(-1))
        self._bind_search_shortcuts()

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Resize:
            if watched is self._content_host:
                self._layout_content()
            elif watched is self.transcript_view:
                self._position_heatmap()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_content()

    def set_result(self, result: TranscriptResult | None) -> None:
        self.transcript_view.set_result(result)
        self.heatmap.set_result(result)
        self._sync_search_status()
        self._update_heatmap_scroll()

    def set_speaker_filter(self, speaker_id: str | None) -> None:
        self.transcript_view.set_speaker_filter(speaker_id)
        self.heatmap.set_speaker_filter(speaker_id)
        self._sync_search_status()
        self._update_heatmap_scroll()

    def highlight_speaker(self, speaker_id: str | None) -> None:
        self.transcript_view.highlight_speaker(speaker_id)
        self.heatmap.set_selected_speaker(speaker_id)

    def goto_adjacent_speaker_entry(self, speaker_id: str, delta: int) -> bool:
        return self.transcript_view.goto_adjacent_speaker_entry(speaker_id, delta)

    def goto_speaker_entry_edge(self, speaker_id: str, *, first: bool) -> bool:
        return self.transcript_view.goto_speaker_entry_edge(speaker_id, first=first)

    def focus_search(self) -> None:
        self.search_bar.focus_input()

    def set_busy(self, busy: bool) -> None:
        self._busy_overlay.setGeometry(self._content_host.rect())
        self._busy_overlay.set_busy(busy)
        if busy:
            self._busy_overlay.raise_()

    def clear(self) -> None:
        self.search_bar.clear_query()
        self.set_result(None)

    def _bind_search_shortcuts(self) -> None:
        find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        find_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        find_shortcut.activated.connect(self.focus_search)
        next_shortcut = QShortcut(QKeySequence.StandardKey.FindNext, self)
        next_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        next_shortcut.activated.connect(lambda: self._goto_search_match(1))
        previous_shortcut = QShortcut(QKeySequence.StandardKey.FindPrevious, self)
        previous_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        previous_shortcut.activated.connect(lambda: self._goto_search_match(-1))

    def _on_search_query(self, query: str) -> None:
        current, total = self.transcript_view.set_search_query(query)
        self.search_bar.set_match_status(current, total)

    def _goto_search_match(self, delta: int) -> None:
        current, total = self.transcript_view.goto_search_match(delta)
        self.search_bar.set_match_status(current, total)

    def _sync_search_status(self) -> None:
        current, total = self.transcript_view.search_status()
        self.search_bar.set_match_status(current, total)

    def _layout_content(self) -> None:
        self.transcript_view.setGeometry(self._content_host.rect())
        self._position_heatmap()
        self._busy_overlay.setGeometry(self._content_host.rect())
        if self._busy_overlay.isVisible():
            self._busy_overlay.raise_()

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
