from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from speaker_transcriber.audio.ffmpeg import stretch_wav_tempo
from speaker_transcriber.audio.tts.queue import SegmentPlaybackQueue
from speaker_transcriber.audio.tts.tempo import clamp_playback_rate
from speaker_transcriber.audio.tts.types import RenderedSegment
from speaker_transcriber.errors import MediaError


class TranscriptTtsPlayer(QObject):
    segment_changed = Signal(int)
    state_changed = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._segments: list[RenderedSegment] = []
        self._queue = SegmentPlaybackQueue()
        self._want_play = False
        self._rate = 1.0
        self._suppress_end = False
        self._pending_seek_fraction: float | None = None
        self._audio = QAudioOutput(self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(self._on_error)

    @property
    def index(self) -> int:
        return self._queue.index

    @property
    def count(self) -> int:
        return self._queue.count

    @property
    def rate(self) -> float:
        return self._rate

    def current_segment(self) -> RenderedSegment | None:
        if not self._segments:
            return None
        return self._segments[self._queue.index]

    def load(self, segments: list[RenderedSegment]) -> None:
        self.stop()
        self._segments = list(segments)
        self._queue.reset(len(self._segments))

    def set_rate(self, rate: float) -> None:
        tempo = clamp_playback_rate(rate)
        if abs(tempo - self._rate) < 1e-6:
            return
        duration_ms = self._player.duration()
        fraction = (
            self._player.position() / duration_ms if duration_ms > 0 else 0.0
        )
        playing = self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        paused = self._player.playbackState() == QMediaPlayer.PlaybackState.PausedState
        self._rate = tempo
        if not self._segments:
            return
        if playing or self._want_play:
            self._want_play = True
            self._play_index(self._queue.index, seek_fraction=fraction)
        elif paused:
            self._load_index(self._queue.index, seek_fraction=fraction)
        else:
            self._load_index(self._queue.index)

    def play(self) -> None:
        if not self._segments:
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PausedState:
            self._want_play = True
            self._player.play()
            self.state_changed.emit("playing")
            return
        self._want_play = True
        self._play_index(self._queue.index)

    def pause(self) -> None:
        if self._player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            return
        self._want_play = False
        self._player.pause()
        self.state_changed.emit("paused")

    def stop(self) -> None:
        self._want_play = False
        self._pending_seek_fraction = None
        self._player.stop()
        self._queue.index = 0
        self.state_changed.emit("stopped")

    def rewind(self) -> None:
        if not self._segments:
            return
        was_playing = self._want_play or (
            self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        self._queue.rewind()
        if was_playing:
            self._want_play = True
            self._play_index(self._queue.index)
        else:
            self._load_index(self._queue.index)

    def _play_index(self, index: int, *, seek_fraction: float | None = None) -> None:
        self._load_index(index, seek_fraction=seek_fraction)
        self._player.play()
        self.state_changed.emit("playing")

    def _load_index(self, index: int, *, seek_fraction: float | None = None) -> None:
        self._queue.index = index
        segment = self._segments[index]
        try:
            path = self._source_path(segment)
        except MediaError as exc:
            self._want_play = False
            self.error.emit(str(exc))
            self.state_changed.emit("stopped")
            return
        self._suppress_end = True
        self._pending_seek_fraction = seek_fraction
        self._player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        self._suppress_end = False
        self.segment_changed.emit(index)

    def _source_path(self, segment: RenderedSegment) -> Path:
        original = Path(segment.wav_path)
        if abs(self._rate - 1.0) < 1e-6:
            return original
        stamped = original.with_name(f"{original.stem}.t{int(round(self._rate * 100)):03d}.wav")
        if stamped.is_file() and stamped.stat().st_mtime >= original.stat().st_mtime:
            return stamped
        stretch_wav_tempo(original, stamped, self._rate, threading.Event())
        return stamped

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            fraction = self._pending_seek_fraction
            if fraction is not None:
                duration_ms = self._player.duration()
                if duration_ms > 0:
                    self._player.setPosition(int(max(0.0, min(fraction, 1.0)) * duration_ms))
                self._pending_seek_fraction = None
            return
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        if self._suppress_end or not self._want_play:
            return
        nxt = self._queue.advance()
        if nxt is None:
            self._want_play = False
            self._queue.index = 0
            self.state_changed.emit("stopped")
            self.finished.emit()
            return
        self._play_index(nxt)

    def _on_error(self, *_args) -> None:
        message = self._player.errorString() or "Playback failed."
        self._want_play = False
        self.error.emit(message)
        self.state_changed.emit("stopped")
