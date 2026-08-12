from __future__ import annotations

from PySide6.QtGui import (
    QColor,
    QTextBlock,
    QTextBlockUserData,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import QTextEdit

from speaker_transcriber.export.common import clock_timestamp, display_speaker, speaker_color_map
from speaker_transcriber.pipeline.types import TranscriptResult
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
        self.setReadOnly(True)
        self.setAcceptRichText(True)
        self.setPlaceholderText("The speaker-labelled transcript will appear here.")
        self._speaker_colors: dict[str, str] = {}
        self._highlighted_speaker: str | None = None

    def set_result(self, result: TranscriptResult | None) -> None:
        self.clear()
        self._highlighted_speaker = None
        self.setExtraSelections([])
        self._speaker_colors = {}
        if result is None:
            return

        colors = speaker_color_map(result)
        self._speaker_colors = colors
        cursor = QTextCursor(self.document())
        first_segment = True

        for segment in result.segments:
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
                overlap = ", ".join(segment.overlapping_speakers)
                cursor.insertText(f"\nOverlapping: {overlap}", overlap_format)

            self._tag_segment_blocks(
                start_block,
                cursor.block(),
                segment.speaker,
                segment.start,
                segment.end,
            )

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
        best_block = None
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
        if best_block is None:
            return
        self._focus_block(best_block)

    def highlight_speaker(self, speaker_id: str | None) -> None:
        self._highlighted_speaker = speaker_id
        if speaker_id is None:
            self.setExtraSelections([])
            return

        color = QColor(self._speaker_colors.get(speaker_id, "#B0BEC5"))
        color.setAlpha(96)
        highlight_format = QTextCharFormat()
        highlight_format.setBackground(color)

        selections: list[QTextEdit.ExtraSelection] = []
        block = self.document().firstBlock()
        while block.isValid():
            data = block.userData()
            if isinstance(data, SegmentBlockData) and data.speaker_id == speaker_id:
                selection = QTextEdit.ExtraSelection()
                selection.cursor = QTextCursor(block)
                selection.cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                selection.cursor.movePosition(
                    QTextCursor.MoveOperation.EndOfBlock,
                    QTextCursor.MoveMode.KeepAnchor,
                )
                selection.format = highlight_format
                selections.append(selection)
            block = block.next()

        self.setExtraSelections(selections)

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

        self._focus_block(target)
        if self._highlighted_speaker == speaker_id:
            self.highlight_speaker(speaker_id)
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
