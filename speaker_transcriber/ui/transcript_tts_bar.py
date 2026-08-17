from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from speaker_transcriber.audio.tts.tempo import (
    MAX_PLAYBACK_RATE,
    MIN_PLAYBACK_RATE,
    clamp_playback_rate,
)
from speaker_transcriber.models.tts_catalog import DEFAULT_TTS_MODEL
from speaker_transcriber.ui.model_combo import ModelComboBox


class TranscriptTtsBar(QWidget):
    prepare_requested = Signal()
    play_requested = Signal()
    pause_requested = Signal()
    stop_requested = Signal()
    rewind_requested = Signal()
    export_requested = Signal()
    rate_changed = Signal(float)
    model_changed = Signal(str)
    add_tts_models_requested = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        include_voice_model: bool = True,
    ) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        self.model_caption = QLabel("Voice model")
        self.model_caption.setObjectName("fieldCaption")
        self.model_combo = ModelComboBox(include_add=True)
        self.model_combo.setMinimumWidth(180)
        self.model_combo.add_models_requested.connect(self.add_tts_models_requested.emit)
        self.model_combo.currentIndexChanged.connect(self._on_model_index_changed)
        if include_voice_model:
            model_row = QHBoxLayout()
            model_row.setContentsMargins(0, 0, 0, 0)
            model_row.setSpacing(6)
            model_row.addWidget(self.model_caption)
            model_row.addWidget(self.model_combo, 1)
            outer.addLayout(model_row)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)

        self.prepare_button = QPushButton("Prepare audio")
        self.play_button = QPushButton("Play")
        self.pause_button = QPushButton("Pause")
        self.stop_button = QPushButton("Stop")
        self.rewind_button = QPushButton("Rewind")
        self.export_button = QPushButton("Export MP3…")
        self.speed_label = QLabel("Speed")
        self.speed_label.setObjectName("fieldCaption")
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(int(MIN_PLAYBACK_RATE * 100), int(MAX_PLAYBACK_RATE * 100))
        self.speed_slider.setSingleStep(5)
        self.speed_slider.setPageStep(25)
        self.speed_slider.setTickInterval(25)
        self.speed_slider.setValue(100)
        self.speed_slider.setMinimumWidth(96)
        self.speed_slider.setMaximumWidth(140)
        self.speed_slider.setToolTip(
            "Playback speed from 0.25× to 4×. Pitch is preserved."
        )
        self.speed_value = QLabel("1.00×")
        self.speed_value.setMinimumWidth(44)
        self.status_label = QLabel("Not prepared")
        self.status_label.setObjectName("fieldCaption")
        self.status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        for button in (
            self.prepare_button,
            self.play_button,
            self.pause_button,
            self.stop_button,
            self.rewind_button,
            self.export_button,
        ):
            controls.addWidget(button)
        controls.addWidget(self.speed_label)
        controls.addWidget(self.speed_slider)
        controls.addWidget(self.speed_value)
        controls.addWidget(self.status_label, 1)
        outer.addLayout(controls)

        self.prepare_button.clicked.connect(self.prepare_requested.emit)
        self.play_button.clicked.connect(self.play_requested.emit)
        self.pause_button.clicked.connect(self.pause_requested.emit)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.rewind_button.clicked.connect(self.rewind_requested.emit)
        self.export_button.clicked.connect(self.export_requested.emit)
        self._rate_timer = QTimer(self)
        self._rate_timer.setSingleShot(True)
        self._rate_timer.setInterval(80)
        self._rate_timer.timeout.connect(self._emit_rate)
        self.speed_slider.valueChanged.connect(self._on_speed_slider)

        self.set_state(has_transcript=False, prepared=False)

    def current_tts_model(self) -> str:
        return self.model_combo.current_value() or DEFAULT_TTS_MODEL

    def playback_rate(self) -> float:
        return clamp_playback_rate(self.speed_slider.value() / 100.0)

    def set_state(
        self,
        *,
        has_transcript: bool,
        prepared: bool,
        rendering: bool = False,
        exporting: bool = False,
        playing: bool = False,
        paused: bool = False,
        status: str | None = None,
        segment_index: int = 0,
        segment_count: int = 0,
    ) -> None:
        busy = rendering or exporting
        self.prepare_button.setEnabled(has_transcript and not busy)
        self.play_button.setEnabled(prepared and not busy and not playing)
        self.pause_button.setEnabled(prepared and playing and not busy)
        self.stop_button.setEnabled(prepared and (playing or paused) and not busy)
        self.rewind_button.setEnabled(prepared and not busy)
        self.export_button.setEnabled(prepared and not busy)
        self.speed_slider.setEnabled(not busy)
        self.model_combo.setEnabled(not busy)
        if status is not None:
            self.status_label.setText(status)
            return
        if exporting:
            self.status_label.setText("Exporting MP3…")
        elif rendering:
            self.status_label.setText("Preparing audio…")
        elif playing and segment_count:
            self.status_label.setText(f"Playing segment {segment_index + 1}/{segment_count}")
        elif paused and segment_count:
            self.status_label.setText(f"Paused at segment {segment_index + 1}/{segment_count}")
        elif prepared:
            self.status_label.setText("Ready")
        elif has_transcript:
            self.status_label.setText("Not prepared")
        else:
            self.status_label.setText("Not prepared")

    def _on_model_index_changed(self, _index: int) -> None:
        model_id = self.model_combo.current_value()
        if model_id:
            self.model_changed.emit(model_id)

    def _on_speed_slider(self, value: int) -> None:
        snapped = int(round(value / 5) * 5)
        snapped = max(self.speed_slider.minimum(), min(self.speed_slider.maximum(), snapped))
        if snapped != value:
            self.speed_slider.blockSignals(True)
            self.speed_slider.setValue(snapped)
            self.speed_slider.blockSignals(False)
        self.speed_value.setText(f"{snapped / 100:.2f}×")
        self._rate_timer.start()

    def _emit_rate(self) -> None:
        self.rate_changed.emit(self.playback_rate())
