from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor,
    QKeyEvent,
    QTextBlock,
    QTextBlockUserData,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import QTextEdit

from speaker_transcriber.export.common import clock_timestamp, display_speaker, speaker_color_map
from speaker_transcriber.pipeline.types import TranscriptResult
from speaker_transcriber.ui.text_search import TextFinder
from speaker_transcriber.ui.theme import Theme


class SegmentBlockData(QTextBlockUserData):
    def __init__(self, speaker_id: str, start: float, end: float) -> None:
        super().__init__()
        self.speaker_id = speaker_id
        self.start = start
        self.end = end


class TranscriptView(QTextEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptRichText(True)
        self.setPlaceholderText("The speaker-labelled transcript will appear here.")
        self._result: TranscriptResult | None = None
        self._speaker_filter: str | None = None
        self._speaker_colors: dict[str, str] = {}
        self._highlighted_speaker: str | None = None
        self._active_entry_start: float | None = None
        self._playback_start: float | None = None
        self._finder = TextFinder()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        speaker_id = self._highlighted_speaker
        modifiers = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
        if speaker_id and modifiers == Qt.KeyboardModifier.NoModifier:
            key = event.key()
            handled = False
            if key in (Qt.Key.Key_Up, Qt.Key.Key_PageUp):
                handled = self.goto_adjacent_speaker_entry(speaker_id, -1)
            elif key in (Qt.Key.Key_Down, Qt.Key.Key_PageDown):
                handled = self.goto_adjacent_speaker_entry(speaker_id, 1)
            elif key == Qt.Key.Key_Home:
                handled = self.goto_speaker_entry_edge(speaker_id, first=True)
            elif key == Qt.Key.Key_End:
                handled = self.goto_speaker_entry_edge(speaker_id, first=False)
            if handled:
                event.accept()
                return
        super().keyPressEvent(event)

    def set_result(self, result: TranscriptResult | None) -> None:
        self._result = result
        self._highlighted_speaker = None
        self._active_entry_start = None
        self._playback_start = None
        if result is None:
            self._speaker_filter = None
        self._render()

    def set_speaker_filter(self, speaker_id: str | None) -> None:
        if self._speaker_filter == speaker_id:
            return
        self._speaker_filter = speaker_id
        self._render()
        if self._highlighted_speaker is not None:
            self._refresh_extra_selections()

    def _render(self) -> None:
        self.clear()
        self.setExtraSelections([])
        self._speaker_colors = {}
        result = self._result
        if result is None:
            self._finder.refresh(self.document())
            self._refresh_extra_selections()
            return

        colors = speaker_color_map(result)
        self._speaker_colors = colors
        cursor = QTextCursor(self.document())
        first_segment = True

        for segment in result.segments:
            if (
                self._speaker_filter is not None
                and segment.speaker != self._speaker_filter
            ):
                continue
            if first_segment:
                first_segment = False
            else:
                cursor.insertBlock()

            start_block = cursor.block()
            speaker = display_speaker(result, segment.speaker)
            color = colors.get(segment.speaker, "#B0BEC5")

            name_format = QTextCharFormat()
            name_format.setForeground(QColor(color))
            name_format.setFontWeight(700)

            time_format = QTextCharFormat()
            time_format.setForeground(QColor(Theme.TEXT_MUTED))

            timestamp = (
                f"[{clock_timestamp(segment.start)} – {clock_timestamp(segment.end)}]"
            )
            if segment.uncertain:
                timestamp += " ⚠ overlap/uncertain"

            body_format = QTextCharFormat()
            body_format.setForeground(QColor(Theme.TEXT))

            cursor.insertText(f"{speaker} ", name_format)
            cursor.insertText(f"{timestamp}\n", time_format)
            cursor.insertText(segment.text, body_format)

            if segment.overlapping_speakers:
                overlap_format = QTextCharFormat()
                overlap_format.setForeground(QColor(Theme.TEXT_MUTED))
                overlap = ", ".join(
                    display_speaker(result, speaker)
                    for speaker in segment.overlapping_speakers
                )
                cursor.insertText(f"\nOverlapping: {overlap}", overlap_format)

            self._tag_segment_blocks(
                start_block,
                cursor.block(),
                segment.speaker,
                segment.start,
                segment.end,
            )

        self._finder.refresh(self.document())
        self._refresh_extra_selections()
        start = QTextCursor(self.document())
        start.movePosition(QTextCursor.MoveOperation.Start)
        self.setTextCursor(start)

    @staticmethod
    def _tag_segment_blocks(
        start_block: QTextBlock,
        end_block: QTextBlock,
        speaker_id: str,
        start: float,
        end: float,
    ) -> None:
        block = start_block
        while block.isValid():
            block.setUserData(SegmentBlockData(speaker_id, start, end))
            if block == end_block:
                break
            block = block.next()

    def scroll_to_time(self, seconds: float) -> None:
        best_block = self._nearest_block_for_time(seconds)
        if best_block is None:
            return
        data = best_block.userData()
        if (
            self._highlighted_speaker is not None
            and isinstance(data, SegmentBlockData)
            and data.speaker_id == self._highlighted_speaker
        ):
            self._active_entry_start = data.start
            self._focus_block(best_block)
            self._refresh_extra_selections()
            return
        self._focus_block(best_block)

    def set_playback_time(self, seconds: float | None) -> None:
        """Highlight the spoken turn and keep it in view during TTS playback."""
        if seconds is None:
            if self._playback_start is None:
                return
            self._playback_start = None
            self._refresh_extra_selections()
            return

        match = self._block_for_start(seconds)
        if match is None:
            if self._playback_start is not None:
                self._playback_start = None
                self._refresh_extra_selections()
            return

        self._playback_start = seconds
        data = match.userData()
        if (
            self._highlighted_speaker is not None
            and isinstance(data, SegmentBlockData)
            and data.speaker_id == self._highlighted_speaker
        ):
            self._active_entry_start = seconds
        self._refresh_extra_selections()
        self._scroll_block_into_follow_view(match)

    def clear_playback(self) -> None:
        self.set_playback_time(None)

    def set_search_query(self, query: str) -> tuple[int, int]:
        self._finder.set_query(
            self.document(),
            query,
            from_position=self.textCursor().position(),
        )
        self._refresh_extra_selections()
        self._reveal_search_match()
        return self.search_status()

    def goto_search_match(self, delta: int) -> tuple[int, int]:
        if self._finder.goto(delta) is not None:
            self._refresh_extra_selections()
            self._reveal_search_match()
        return self.search_status()

    def search_status(self) -> tuple[int, int]:
        return self._finder.status()

    def highlight_speaker(self, speaker_id: str | None) -> None:
        self._highlighted_speaker = speaker_id
        if speaker_id is None:
            self._active_entry_start = None
            self._refresh_extra_selections()
            return

        cursor_data = self.textCursor().block().userData()
        if (
            isinstance(cursor_data, SegmentBlockData)
            and cursor_data.speaker_id == speaker_id
        ):
            self._active_entry_start = cursor_data.start
        else:
            self._active_entry_start = None
        self._refresh_extra_selections()

    def _speaker_fill_color(self, speaker_id: str, *, active: bool) -> QColor:
        tint = QColor(self._speaker_colors.get(speaker_id, "#B0BEC5"))
        base = QColor(Theme.WINDOW)
        # Mix the speaker hue into the dark window color so white body text
        # stays readable. Active entries get a stronger tint, not a lighter one.
        amount = 0.42 if active else 0.22
        return QColor(
            int(base.red() + (tint.red() - base.red()) * amount),
            int(base.green() + (tint.green() - base.green()) * amount),
            int(base.blue() + (tint.blue() - base.blue()) * amount),
            235 if active else 170,
        )

    def _refresh_extra_selections(self) -> None:
        selections = self._segment_extra_selections()
        selections.extend(self._finder.extra_selections())
        self.setExtraSelections(selections)

    def _segment_extra_selections(self) -> list[QTextEdit.ExtraSelection]:
        speaker_id = self._highlighted_speaker
        playback_start = self._playback_start
        if speaker_id is None and playback_start is None:
            return []

        selections: list[QTextEdit.ExtraSelection] = []
        block = self.document().firstBlock()
        while block.isValid():
            data = block.userData()
            if isinstance(data, SegmentBlockData):
                is_playback = (
                    playback_start is not None and data.start == playback_start
                )
                is_speaker = speaker_id is not None and data.speaker_id == speaker_id
                if is_playback or is_speaker:
                    active = is_playback or (
                        self._active_entry_start is not None
                        and data.start == self._active_entry_start
                    )
                    selections.append(
                        self._block_selection(
                            block,
                            self._block_fill_format(data.speaker_id, active=active),
                        )
                    )
            block = block.next()
        return selections

    def _block_fill_format(self, speaker_id: str, *, active: bool) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setBackground(self._speaker_fill_color(speaker_id, active=active))
        fmt.setProperty(QTextFormat.Property.FullWidthSelection, True)
        return fmt

    def _block_selection(
        self, block: QTextBlock, fmt: QTextCharFormat
    ) -> QTextEdit.ExtraSelection:
        selection = QTextEdit.ExtraSelection()
        selection.cursor = QTextCursor(block)
        selection.cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        selection.cursor.movePosition(
            QTextCursor.MoveOperation.EndOfBlock,
            QTextCursor.MoveMode.KeepAnchor,
        )
        selection.format = fmt
        return selection

    def _nearest_block_for_time(self, seconds: float) -> QTextBlock | None:
        best_block: QTextBlock | None = None
        best_distance = float("inf")
        block = self.document().firstBlock()
        while block.isValid():
            data = block.userData()
            if isinstance(data, SegmentBlockData):
                distance = abs(data.start - seconds)
                if distance < best_distance:
                    best_distance = distance
                    best_block = block
            block = block.next()
        return best_block

    def _block_for_start(self, start: float) -> QTextBlock | None:
        block = self.document().firstBlock()
        while block.isValid():
            data = block.userData()
            if isinstance(data, SegmentBlockData) and data.start == start:
                return block
            block = block.next()
        return None

    def _scroll_block_into_follow_view(self, block: QTextBlock) -> None:
        layout = self.document().documentLayout()
        if layout is None:
            return
        block_rect = layout.blockBoundingRect(block)
        viewport_height = self.viewport().height()
        margin = max(16, min(48, viewport_height // 6)) if viewport_height > 0 else 16
        target = int(block_rect.top()) - margin
        bar = self.verticalScrollBar()
        bar.setValue(max(bar.minimum(), min(target, bar.maximum())))

    def _reveal_search_match(self) -> None:
        match = self._finder.current_cursor()
        if match is None:
            return
        cursor = QTextCursor(self.document())
        cursor.setPosition(match.selectionStart())
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def goto_adjacent_speaker_entry(self, speaker_id: str, delta: int) -> bool:
        anchors = self._speaker_entry_anchors(speaker_id)
        if not anchors:
            return False

        cursor_block_position = self.textCursor().block().position()
        target: QTextBlock | None = None
        if delta > 0:
            for block in anchors:
                if block.position() > cursor_block_position:
                    target = block
                    break
            if target is None:
                target = anchors[0]
        else:
            for block in reversed(anchors):
                if block.position() < cursor_block_position:
                    target = block
                    break
            if target is None:
                target = anchors[-1]

        return self._focus_speaker_entry(speaker_id, target)

    def goto_speaker_entry_edge(self, speaker_id: str, *, first: bool) -> bool:
        anchors = self._speaker_entry_anchors(speaker_id)
        if not anchors:
            return False
        target = anchors[0] if first else anchors[-1]
        return self._focus_speaker_entry(speaker_id, target)

    def _focus_speaker_entry(self, speaker_id: str, target: QTextBlock) -> bool:
        data = target.userData()
        self._active_entry_start = (
            data.start if isinstance(data, SegmentBlockData) else None
        )
        self._highlighted_speaker = speaker_id
        self._focus_block(target)
        self._refresh_extra_selections()
        return True

    def _speaker_entry_anchors(self, speaker_id: str) -> list[QTextBlock]:
        anchors: list[QTextBlock] = []
        seen_starts: set[float] = set()
        block = self.document().firstBlock()
        while block.isValid():
            data = block.userData()
            if (
                isinstance(data, SegmentBlockData)
                and data.speaker_id == speaker_id
                and data.start not in seen_starts
            ):
                seen_starts.add(data.start)
                anchors.append(block)
            block = block.next()
        return anchors

    def _focus_block(self, block: QTextBlock) -> None:
        cursor = QTextCursor(block)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def append_summary(self, summary: str) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertBlock()
        heading = QTextCharFormat()
        heading.setForeground(QColor(Theme.ACCENT))
        heading.setFontWeight(700)
        cursor.insertText("Summary\n", heading)
        body = QTextCharFormat()
        body.setForeground(QColor(Theme.TEXT))
        cursor.insertText(summary, body)
