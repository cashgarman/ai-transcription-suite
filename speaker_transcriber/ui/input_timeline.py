from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from speaker_transcriber.export.common import clock_timestamp
from speaker_transcriber.ui.theme import Theme


SEGMENT_COLORS = (
    "#7EC8D4",
    "#FFB74D",
    "#81C784",
    "#CE93D8",
    "#E57373",
    "#4DB6AC",
    "#FFD54F",
    "#90A4AE",
)


@dataclass
class TimelineSegment:
    path: Path
    duration_seconds: float | None = None


class InputTimelineWidget(QWidget):
    order_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(92)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self._segments: list[TimelineSegment] = []
        self._drag_index: int | None = None
        self._hover_index: int | None = None
        self._drop_index: int | None = None
        self._selected_indices: set[int] = set()
        self.setToolTip(
            "Drag segments to change merge order. Files are joined left to right."
        )

    def selected_paths(self) -> list[Path]:
        return [
            self._segments[index].path
            for index in sorted(self._selected_indices)
            if 0 <= index < len(self._segments)
        ]

    def clear_selection(self) -> None:
        self._selected_indices.clear()
        self.update()

    def paths(self) -> list[Path]:
        return [segment.path for segment in self._segments]

    def set_paths(self, paths: list[Path]) -> None:
        existing = {str(segment.path.resolve()): segment for segment in self._segments}
        self._segments = []
        for path in paths:
            resolved = str(path.resolve())
            prior = existing.get(resolved)
            if prior is not None:
                self._segments.append(TimelineSegment(path=path, duration_seconds=prior.duration_seconds))
            else:
                self._segments.append(TimelineSegment(path=path))
        self._drag_index = None
        self._hover_index = None
        self._drop_index = None
        self.update()

    def append_paths(self, paths: list[Path]) -> None:
        current = self.paths()
        seen = {str(path.resolve()) for path in current}
        for path in paths:
            resolved = str(path.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            current.append(path)
        self.set_paths(current)

    def remove_selected(self, paths: list[Path]) -> None:
        remove = {str(path.resolve()) for path in paths}
        self.set_paths(
            [segment.path for segment in self._segments if str(segment.path.resolve()) not in remove]
        )
        self.order_changed.emit()

    def set_duration(self, path: Path, duration_seconds: float) -> None:
        resolved = str(path.resolve())
        for segment in self._segments:
            if str(segment.path.resolve()) == resolved:
                segment.duration_seconds = duration_seconds
                self.update()
                return

    def _effective_duration(self, segment: TimelineSegment) -> float:
        if segment.duration_seconds is not None and segment.duration_seconds > 0:
            return segment.duration_seconds
        return 1.0

    def _total_duration(self) -> float:
        if not self._segments:
            return 0.0
        return sum(self._effective_duration(segment) for segment in self._segments)

    def _layout_segments(self) -> list[tuple[int, int, int, int]]:
        if not self._segments:
            return []
        total = self._total_duration()
        margin = 8
        track_top = 28
        track_height = 34
        width = max(self.width() - margin * 2, 1)
        layouts: list[tuple[int, int, int, int]] = []
        x = margin
        for segment in self._segments:
            fraction = self._effective_duration(segment) / total
            segment_width = max(int(width * fraction), 48)
            layouts.append((x, track_top, segment_width, track_height))
            x += segment_width + 4
        return layouts

    def _index_at(self, point: QPoint) -> int | None:
        layouts = self._layout_segments()
        for index, rect in enumerate(layouts):
            x, y, width, height = rect
            if x <= point.x() <= x + width and y <= point.y() <= y + height:
                return index
        return None

    def _drop_index_for(self, point: QPoint) -> int:
        if not self._segments:
            return 0
        layouts = self._layout_segments()
        for index, rect in enumerate(layouts):
            x, _, width, _ = rect
            midpoint = x + width / 2
            if point.x() < midpoint:
                return index
        return len(self._segments)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        index = self._index_at(event.position().toPoint())
        if index is None:
            self._selected_indices.clear()
            self.update()
            return
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            if index in self._selected_indices:
                self._selected_indices.remove(index)
            else:
                self._selected_indices.add(index)
        elif modifiers & Qt.KeyboardModifier.ShiftModifier and self._selected_indices:
            start = min(self._selected_indices)
            end = max(index, start)
            self._selected_indices = set(range(min(start, index), end + 1))
        else:
            self._selected_indices = {index}
        self._drag_index = index
        self._drop_index = index
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if self._drag_index is not None:
            self._drop_index = self._drop_index_for(point)
            self.update()
            return
        hover = self._index_at(point)
        if hover != self._hover_index:
            self._hover_index = hover
            self.update()
        if hover is not None:
            segment = self._segments[hover]
            duration = (
                clock_timestamp(segment.duration_seconds)
                if segment.duration_seconds
                else "duration unknown"
            )
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"{segment.path.name}\n{duration}\nDrag to reorder",
                self,
            )

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._drag_index is None:
            return
        release_point = event.position().toPoint()
        drop_index = self._drop_index_for(release_point)
        drag_index = self._drag_index
        start_index = self._index_at(release_point)
        self._drag_index = None
        self._drop_index = None
        if start_index == drag_index and drop_index == drag_index:
            self.update()
            return
        if drag_index != drop_index and 0 <= drag_index < len(self._segments):
            segment = self._segments.pop(drag_index)
            if drop_index > drag_index:
                drop_index -= 1
            drop_index = max(0, min(drop_index, len(self._segments)))
            self._segments.insert(drop_index, segment)
            self._selected_indices = {drop_index}
            self.order_changed.emit()
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(Theme.SURFACE_SUNKEN))

        if not self._segments:
            painter.setPen(QColor(Theme.TEXT_MUTED))
            painter.drawText(
                self.rect().adjusted(12, 0, -12, 0),
                int(Qt.AlignmentFlag.AlignCenter),
                "Add or drop audio/video files to build the merge timeline",
            )
            return

        painter.setPen(QColor(Theme.TEXT_DIM))
        painter.setFont(QFont(self.font().family(), 9))
        painter.drawText(10, 18, "Merge order →")
        total = self._total_duration()
        painter.drawText(
            self.width() - 140,
            18,
            f"Total {clock_timestamp(total)}",
        )

        layouts = self._layout_segments()
        for index, (segment, rect) in enumerate(zip(self._segments, layouts)):
            x, y, width, height = rect
            color = QColor(SEGMENT_COLORS[index % len(SEGMENT_COLORS)])
            if self._drag_index == index:
                color = color.lighter(120)
            elif self._hover_index == index:
                color = color.lighter(108)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(x, y, width, height, 6, 6)

            if index in self._selected_indices:
                painter.setPen(QPen(QColor(Theme.TEXT), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(x + 1, y + 1, width - 2, height - 2, 6, 6)

            if self._drop_index == index and self._drag_index is not None:
                painter.setPen(QPen(QColor(Theme.ACCENT), 2))
                painter.drawLine(x - 2, y - 4, x - 2, y + height + 4)

            painter.setPen(QColor(Theme.WINDOW))
            label = f"{index + 1}. {segment.path.name}"
            metrics = QFontMetrics(painter.font())
            elided = metrics.elidedText(label, Qt.TextElideMode.ElideRight, width - 10)
            painter.drawText(x + 6, y + 15, elided)
            duration_text = (
                clock_timestamp(segment.duration_seconds)
                if segment.duration_seconds
                else "…"
            )
            painter.drawText(x + 6, y + 28, duration_text)

        if (
            self._drop_index == len(self._segments)
            and self._drag_index is not None
            and layouts
        ):
            last = layouts[-1]
            line_x = last[0] + last[2] + 2
            painter.setPen(QPen(QColor(Theme.ACCENT), 2))
            painter.drawLine(line_x, last[1] - 4, line_x, last[1] + last[3] + 4)

        painter.end()
