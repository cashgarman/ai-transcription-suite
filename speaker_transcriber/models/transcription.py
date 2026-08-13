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
            segment_iterator, info = batched_model.transcribe(
                str(audio_path),
                batch_size=options.batch_size,
                language=language,
                word_timestamps=False,
                vad_filter=True,
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
            if not segments:
                raise NoSpeechError(
                    "No speech was detected. Check that the file contains audible speech."
                )
            if on_progress:
                on_progress(1.0)
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
