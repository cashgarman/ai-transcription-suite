from __future__ import annotations


class SegmentPlaybackQueue:
    """Index helper for sequential TTS clips. Rewind goes to the previous segment."""

    def __init__(self, count: int = 0) -> None:
        self.count = max(0, count)
        self.index = 0

    def reset(self, count: int) -> None:
        self.count = max(0, count)
        self.index = 0

    def rewind(self) -> int:
        if self.index > 0:
            self.index -= 1
        return self.index

    def advance(self) -> int | None:
        if self.index + 1 >= self.count:
            return None
        self.index += 1
        return self.index
