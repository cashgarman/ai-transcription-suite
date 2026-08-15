from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path
from typing import Callable

from speaker_transcriber.errors import NoSpeechError, ProcessingCancelled
from speaker_transcriber.models.model_manager import ModelManager
from speaker_transcriber.pipeline.types import ProcessingOptions, RawSegment


LOGGER = logging.getLogger("speaker_transcriber.transcription")

# Whisper often emits these on silent/non-speech audio when VAD is disabled.
_HALLUCINATION_PHRASES = frozenset(
    {
        "thank you",
        "thank you.",
        "thanks for watching",
        "thanks for watching.",
        "please subscribe",
        "see you next time",
        "bye",
        "goodbye",
    }
)


def _normalize_phrase(text: str) -> str:
    return text.strip().lower().rstrip(".")


def _looks_like_hallucinated_transcript(
    segments: list[RawSegment],
    duration_seconds: float,
) -> bool:
    if len(segments) < 3:
        return False
    phrases = {_normalize_phrase(segment.text) for segment in segments}
    if len(phrases) != 1:
        return False
    phrase = next(iter(phrases))
    if phrase not in _HALLUCINATION_PHRASES:
        return False
    if len(segments) >= 3:
        gaps = [
            segments[index + 1].start - segments[index].start
            for index in range(len(segments) - 1)
        ]
        if gaps and all(25.0 <= gap <= 35.0 for gap in gaps):
            return True
    spoken = sum(max(segment.end - segment.start, 0.0) for segment in segments)
    return spoken < 60.0 and duration_seconds > 120.0


class Transcriber:
    def __init__(self, model_manager: ModelManager) -> None:
        self.model_manager = model_manager

    def transcribe(
        self,
        audio_path: Path,
        options: ProcessingOptions,
        cancel_event: threading.Event,
        on_progress: Callable[[float], None] | None = None,
    ) -> tuple[list[RawSegment], str]:
        import torch
        from faster_whisper import BatchedInferencePipeline, WhisperModel

        if options.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA is unavailable. Install an NVIDIA driver and a CUDA-enabled PyTorch build, "
                "or select the CPU device."
            )
        language = None if options.language == "auto" else options.language
        compute_type = (
            "int8"
            if options.device == "cpu" and options.compute_type == "int8_float16"
            else options.compute_type
        )
        LOGGER.info(
            "Loading faster-whisper model=%s device=%s compute_type=%s batch_size=%d",
            options.model,
            options.device,
            compute_type,
            options.batch_size,
        )
        model = None
        batched_model = None
        try:
            from speaker_transcriber.debug_log import agent_log

            venv_cudnn = (
                Path(sys.prefix)
                / "Lib"
                / "site-packages"
                / "nvidia"
                / "cudnn"
                / "bin"
                / "cudnn_ops_infer64_8.dll"
            )
            agent_log(
                "transcription.py:transcribe",
                "loading whisper model",
                {
                    "device": options.device,
                    "model": options.model,
                    "cudnn_dll_venv_exists": venv_cudnn.exists(),
                    "path_contains_cudnn": "nvidia\\cudnn\\bin"
                    in os.environ.get("PATH", "").lower(),
                },
                "H4",
            )
            try:
                model = WhisperModel(
                    options.model,
                    device=options.device,
                    compute_type=compute_type,
                )
            except Exception as exc:
                agent_log(
                    "transcription.py:transcribe",
                    "whisper model load failed",
                    {"error_type": type(exc).__name__, "error": str(exc)[:300]},
                    "H4",
                )
                message = str(exc).lower()
                if "localentrynotfounderror" in message or "connection" in message:
                    raise RuntimeError(
                        "Could not download the Whisper model from Hugging Face. "
                        "This is usually a Windows SSL or network issue on the first run. "
                        "Add HF_HUB_INSECURE_SSL=1 to your .env file, restart the app, "
                        "and try again. After the model is cached locally you can remove it."
                    ) from exc
                raise
            batched_model = BatchedInferencePipeline(model=model)
            segments, info = self._collect_segments(
                batched_model,
                audio_path,
                options,
                cancel_event,
                on_progress,
                language,
                vad_filter=True,
            )
            duration = max(float(info.duration), 0.001)
            if not segments or _looks_like_hallucinated_transcript(segments, duration):
                if segments:
                    LOGGER.info(
                        "Discarding likely silent-audio hallucinations; retrying with relaxed VAD"
                    )
                else:
                    LOGGER.info(
                        "No speech with default VAD; retrying with relaxed VAD"
                    )
                from faster_whisper.vad import VadOptions

                relaxed_vad = VadOptions(
                    threshold=0.35,
                    min_silence_duration_ms=500,
                    speech_pad_ms=200,
                )
                segments, info = self._collect_segments(
                    batched_model,
                    audio_path,
                    options,
                    cancel_event,
                    on_progress,
                    language,
                    vad_filter=True,
                    vad_parameters=relaxed_vad,
                )
                duration = max(float(info.duration), 0.001)
            if not segments or _looks_like_hallucinated_transcript(segments, duration):
                message = (
                    "No speech was detected. Check that the file contains audible speech."
                )
                if options.max_input_duration_seconds is not None:
                    message = (
                        "No speech was detected in the first 10 minutes of this "
                        "recording. If the conversation starts later, upgrade to "
                        "Personal for the full recording."
                    )
                raise NoSpeechError(message)
            detected_language = info.language or language or "unknown"
            LOGGER.info(
                "Transcription complete: %d segments, language=%s",
                len(segments),
                detected_language,
            )
            return segments, detected_language
        finally:
            if batched_model is not None:
                del batched_model
            if model is not None:
                del model
            self.model_manager.clear_cuda()

    def _collect_segments(
        self,
        batched_model,
        audio_path: Path,
        options: ProcessingOptions,
        cancel_event: threading.Event,
        on_progress: Callable[[float], None] | None,
        language: str | None,
        *,
        vad_filter: bool,
        vad_parameters=None,
        clip_timestamps: list[dict[str, float]] | None = None,
    ):
        transcribe_kwargs = {
            "batch_size": options.batch_size,
            "language": language,
            "word_timestamps": False,
            "vad_filter": vad_filter,
        }
        if vad_parameters is not None:
            transcribe_kwargs["vad_parameters"] = vad_parameters
        if clip_timestamps is not None:
            transcribe_kwargs["clip_timestamps"] = clip_timestamps
        segment_iterator, info = batched_model.transcribe(
            str(audio_path),
            **transcribe_kwargs,
        )
        segments: list[RawSegment] = []
        duration = max(float(info.duration), 0.001)
        for segment in segment_iterator:
            if cancel_event.is_set():
                raise ProcessingCancelled()
            text = segment.text.strip()
            if text:
                segments.append(
                    RawSegment(
                        start=float(segment.start),
                        end=float(segment.end),
                        text=text,
                    )
                )
            if on_progress:
                on_progress(min(float(segment.end) / duration, 1.0))
        if segments and on_progress:
            on_progress(1.0)
        return segments, info
