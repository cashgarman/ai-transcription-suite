from __future__ import annotations

import logging
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Callable

from speaker_transcriber.audio.preprocessing import normalized_media
from speaker_transcriber.audio.sources import MediaSource
from speaker_transcriber.errors import ProcessingCancelled
from speaker_transcriber.models.alignment import Aligner
from speaker_transcriber.models.diarization import Diarizer
from speaker_transcriber.models.model_manager import ModelManager
from speaker_transcriber.models.transcription import Transcriber
from speaker_transcriber.pipeline.speaker_assignment import assign_speakers
from speaker_transcriber.pipeline.transcript_merger import merge_words
from speaker_transcriber.pipeline.types import (
    ProcessingOptions,
    ProgressUpdate,
    RawSegment,
    TranscriptResult,
)


LOGGER = logging.getLogger("speaker_transcriber.processor")
STAGES = {
    "loading_media": (0.00, 0.02),
    "extracting_audio": (0.02, 0.08),
    "loading_whisper": (0.10, 0.05),
    "transcribing": (0.15, 0.35),
    "aligning": (0.50, 0.20),
    "diarizing": (0.70, 0.20),
    "assigning_speakers": (0.90, 0.05),
    "formatting": (0.95, 0.05),
}


class TranscriptionProcessor:
    def __init__(
        self,
        model_manager: ModelManager | None = None,
        transcriber: Transcriber | None = None,
        aligner: Aligner | None = None,
        diarizer: Diarizer | None = None,
    ) -> None:
        self.model_manager = model_manager or ModelManager()
        self.transcriber = transcriber or Transcriber(self.model_manager)
        self.aligner = aligner or Aligner(self.model_manager)
        self.diarizer = diarizer or Diarizer(self.model_manager)

    def run(
        self,
        input_path: str | Path | list[str | Path],
        options: ProcessingOptions,
        cancel_event: threading.Event | None = None,
        on_progress: Callable[[ProgressUpdate], None] | None = None,
    ) -> TranscriptResult:
        self._validate_options(options)
        cancel = cancel_event or threading.Event()
        started = time.monotonic()
        media_source = MediaSource.parse(input_path)
        media_source.validate()
        decisions: list[str] = []
        raw_segments: list[RawSegment] = []
        language = options.language
        duration = 0.0
        active_stage: str | None = None
        active_stage_started = started

        def emit(stage: str, fraction: float, message: str) -> None:
            nonlocal active_stage, active_stage_started
            now = time.monotonic()
            if stage != active_stage:
                if active_stage is not None:
                    LOGGER.info(
                        "Stage %s completed in %.2f seconds",
                        active_stage,
                        now - active_stage_started,
                    )
                LOGGER.info("Stage %s started", stage)
                active_stage = stage
                active_stage_started = now
            if on_progress is None:
                return
            base, weight = STAGES[stage]
            used, total = self.model_manager.get_vram_info()
            clamped = max(0.0, min(fraction, 1.0))
            on_progress(
                ProgressUpdate(
                    stage=stage,
                    progress=min(base + weight * clamped, 1.0),
                    message=message,
                    elapsed_seconds=time.monotonic() - started,
                    vram_used_mb=used,
                    vram_total_mb=total,
                    stage_fraction=clamped,
                )
            )

        def partial_result() -> TranscriptResult | None:
            if not raw_segments:
                return None
            words = assign_speakers(raw_segments, [], options.inherit_speaker_threshold_seconds)
            blocks = merge_words(
                words,
                options.merge_gap_seconds,
                options.max_block_duration_seconds,
            )
            return TranscriptResult(
                source_file=media_source.source_file_for_result(),
                source_files=media_source.source_files_for_result(),
                language=language,
                duration_seconds=duration,
                segments=blocks,
                fallback_config={"decisions": decisions},
            )

        try:
            self._check_cancel(cancel)
            if options.hf_token:
                from speaker_transcriber.huggingface_setup import prefetch_diarization_models

                emit(
                    "loading_media",
                    0.0,
                    "Caching pyannote diarization models",
                )
                prefetch_diarization_models(options.hf_token, options.diarization_model)
            emit(
                "loading_media",
                0.0,
                "Inspecting media files" if media_source.is_multi else "Inspecting media file",
            )

            def extraction_progress(value: float) -> None:
                message = (
                    "Merging and extracting mono 16 kHz audio"
                    if media_source.is_multi
                    else "Extracting mono 16 kHz audio"
                )
                emit("extracting_audio", value, message)

            with normalized_media(media_source.paths, cancel, extraction_progress) as (
                audio_path,
                media,
            ):
                duration = media.duration_seconds
                self._check_cancel(cancel)
                emit("loading_whisper", 0.0, f"Loading Whisper model {options.model}")

                def transcription_operation(
                    candidate: ProcessingOptions,
                ) -> tuple[list[RawSegment], str]:
                    return self.transcriber.transcribe(
                        audio_path,
                        candidate,
                        cancel,
                        lambda value: emit("transcribing", value, "Transcribing speech"),
                    )

                (raw_segments, language), chosen = self.model_manager.run_transcription_with_fallback(
                    transcription_operation,
                    options,
                    decisions,
                )
                options = chosen
                emit("transcribing", 1.0, "Transcription complete")
                self._check_cancel(cancel)

                alignment_available = False
                aligned_segments = raw_segments
                try:
                    def alignment_operation(device: str) -> list[RawSegment]:
                        align_model = options.alignment_model
                        if str(align_model or "").strip().lower() in {"", "auto"}:
                            align_model = None
                        return self.aligner.align(
                            audio_path,
                            raw_segments,
                            language,
                            device,
                            cancel,
                            lambda value: emit(
                                "aligning",
                                value,
                                "Aligning word timestamps",
                            ),
                            model_name=align_model,
                        )

                    aligned_segments, alignment_device = (
                        self.model_manager.run_device_stage_with_fallback(
                            alignment_operation,
                            options.alignment_device,
                            "alignment",
                            decisions,
                        )
                    )
                    options = replace(options, alignment_device=alignment_device)
                    alignment_available = True
                except ProcessingCancelled:
                    raise
                except Exception:
                    LOGGER.exception(
                        "Alignment failed; continuing with segment-level timestamps."
                    )
                    decisions.append(
                        "Alignment failed; segment-level timestamps were preserved."
                    )
                emit("aligning", 1.0, "Alignment stage complete")
                self._check_cancel(cancel)

                diarization_available = False
                diarization = []
                try:
                    def diarization_operation(device: str):
                        return self.diarizer.diarize(
                            audio_path,
                            options,
                            device,
                            cancel,
                            lambda value: emit(
                                "diarizing",
                                value,
                                "Identifying speaker turns",
                            ),
                        )

                    diarization, diarization_device = (
                        self.model_manager.run_device_stage_with_fallback(
                            diarization_operation,
                            options.diarization_device,
                            "diarization",
                            decisions,
                        )
                    )
                    options = replace(options, diarization_device=diarization_device)
                    diarization_available = bool(diarization)
                except ProcessingCancelled:
                    raise
                except Exception as exc:
                    LOGGER.error(
                        "Diarization failed; preserving the plain transcript: %s",
                        exc,
                    )
                    decisions.append(f"Diarization unavailable: {exc}")
                emit("diarizing", 1.0, "Diarization stage complete")
                self._check_cancel(cancel)

                emit("assigning_speakers", 0.0, "Assigning words to speakers")
                words = assign_speakers(
                    aligned_segments,
                    diarization,
                    options.inherit_speaker_threshold_seconds,
                )
                emit("assigning_speakers", 1.0, "Speaker assignment complete")
                self._check_cancel(cancel)
                emit("formatting", 0.0, "Formatting transcript")
                blocks = merge_words(
                    words,
                    options.merge_gap_seconds,
                    options.max_block_duration_seconds,
                )
                speaker_ids = sorted(
                    {block.speaker for block in blocks if block.speaker != "UNKNOWN"}
                )
                speakers = {
                    speaker_id: f"Speaker {index}"
                    for index, speaker_id in enumerate(speaker_ids, start=1)
                }
                result = TranscriptResult(
                    source_file=media_source.source_file_for_result(),
                    source_files=media_source.source_files_for_result(),
                    language=language,
                    duration_seconds=duration,
                    speakers=speakers,
                    segments=blocks,
                    alignment_available=alignment_available,
                    diarization_available=diarization_available,
                    fallback_config={
                        "model": options.model,
                        "batch_size": options.batch_size,
                        "alignment_device": options.alignment_device,
                        "diarization_device": options.diarization_device,
                        "decisions": decisions,
                    },
                )
                emit("formatting", 1.0, "Transcript ready")
                LOGGER.info(
                    "Stage formatting completed in %.2f seconds",
                    time.monotonic() - active_stage_started,
                )
                LOGGER.info(
                    "Processing completed in %.2f seconds",
                    time.monotonic() - started,
                )
                return result
        except ProcessingCancelled as exc:
            self.model_manager.clear_cuda()
            if exc.partial_result is None:
                exc.partial_result = partial_result()
            raise
        finally:
            self.model_manager.clear_cuda()

    @staticmethod
    def _check_cancel(cancel_event: threading.Event) -> None:
        if cancel_event.is_set():
            raise ProcessingCancelled()

    @staticmethod
    def _validate_options(options: ProcessingOptions) -> None:
        if options.batch_size < 1:
            raise ValueError("Batch size must be at least 1.")
        if options.num_speakers is not None and (
            options.min_speakers is not None or options.max_speakers is not None
        ):
            raise ValueError("Exact speaker count cannot be combined with min/max speakers.")
        if (
            options.min_speakers is not None
            and options.max_speakers is not None
            and options.min_speakers > options.max_speakers
        ):
            raise ValueError("Minimum speakers cannot exceed maximum speakers.")
