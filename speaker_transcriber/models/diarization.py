from __future__ import annotations

import logging
import threading
import time
from pickle import UnpicklingError
from pathlib import Path
from typing import Callable

from speaker_transcriber.debug_log import agent_log
from speaker_transcriber.errors import AuthenticationError, ProcessingCancelled
from speaker_transcriber.huggingface_compat import patch_hf_hub_use_auth_token
from speaker_transcriber.huggingface_setup import (
    configure_huggingface_client,
    is_retryable_download_error,
    unsupported_diarization_model_message,
)
from speaker_transcriber.models.model_manager import ModelManager
from speaker_transcriber.pipeline.types import DiarizationSegment, ProcessingOptions
from speaker_transcriber.pytorch_compat import patch_torch_load_weights_only
from speaker_transcriber.speechbrain_compat import patch_speechbrain_lazy_modules


LOGGER = logging.getLogger("speaker_transcriber.diarization")
MODEL_ID = "pyannote/speaker-diarization-3.1"
MODEL_URL = f"https://huggingface.co/{MODEL_ID}"
SEGMENTATION_URL = "https://huggingface.co/pyannote/segmentation-3.0"


def _model_url(model_id: str | None) -> str:
    name = (model_id or MODEL_ID).strip() or MODEL_ID
    return f"https://huggingface.co/{name}"


def _is_auth_failure(exc: BaseException) -> bool:
    if isinstance(exc, (TypeError, UnpicklingError)):
        return False
    message = str(exc).lower()
    return any(
        term in message
        for term in ("401", "403", "gated", "access denied", "unauthorized", "forbidden")
    )


def _is_torch_weights_only_failure(exc: BaseException) -> bool:
    message = str(exc).lower()
    return isinstance(exc, UnpicklingError) or "weights only load failed" in message


class Diarizer:
    def __init__(self, model_manager: ModelManager) -> None:
        self.model_manager = model_manager

    def diarize(
        self,
        audio_path: Path,
        options: ProcessingOptions,
        device: str,
        cancel_event: threading.Event,
        on_progress: Callable[[float], None] | None = None,
    ) -> list[DiarizationSegment]:
        import torch
        from pyannote.audio import Pipeline

        if not options.hf_token:
            raise AuthenticationError(
                "Speaker diarization needs a Hugging Face token. Set HF_TOKEN in "
                f"{_model_url(options.diarization_model)} and accept the model terms."
            )
        if cancel_event.is_set():
            raise ProcessingCancelled()

        configure_huggingface_client()
        patch_hf_hub_use_auth_token()
        patch_torch_load_weights_only()
        patch_speechbrain_lazy_modules()
        agent_log(
            "diarization.py:diarize",
            "starting diarization",
            {"hf_token_present": True, "device": device},
            "H4",
        )

        pipeline = None
        try:
            LOGGER.info("Loading pyannote diarization model on %s", device)
            try:
                pipeline = self._load_pipeline(options.hf_token, options.diarization_model)
            except Exception as exc:
                agent_log(
                    "diarization.py:diarize",
                    "pipeline load failed",
                    {"error_type": type(exc).__name__, "error": str(exc)[:300]},
                    "H4",
                )
                model_url = _model_url(options.diarization_model)
                if _is_auth_failure(exc):
                    raise AuthenticationError(
                        "Hugging Face authentication failed or pyannote model access was "
                        f"not accepted. Verify HF_TOKEN and accept the terms at {model_url} "
                        f"and {SEGMENTATION_URL}."
                    ) from exc
                if _is_torch_weights_only_failure(exc):
                    raise RuntimeError(
                        "Pyannote could not load its checkpoint with the installed PyTorch "
                        "version. Restart the app so the PyTorch compatibility patch can apply."
                    ) from exc
                load_error = str(exc).lower()
                if "config.yaml" in load_error and (
                    "entry not found" in load_error or "404" in load_error
                ):
                    raise RuntimeError(
                        unsupported_diarization_model_message(options.diarization_model)
                    ) from exc
                if is_retryable_download_error(exc):
                    raise RuntimeError(
                        "Could not download pyannote diarization models from Hugging Face. "
                        "Keep HF_HUB_INSECURE_SSL=1 in .env until models are cached, then "
                        "restart and try again."
                    ) from exc
                raise
            if pipeline is None:
                raise AuthenticationError(
                    "Pyannote could not load the gated model. Verify HF_TOKEN and accept "
                    f"the terms at {_model_url(options.diarization_model)} and {SEGMENTATION_URL}."
                )
            pipeline.to(torch.device(device))
            if on_progress:
                on_progress(0.2)
            arguments: dict[str, int] = {}
            if options.num_speakers is not None:
                arguments["num_speakers"] = options.num_speakers
            else:
                if options.min_speakers is not None:
                    arguments["min_speakers"] = options.min_speakers
                if options.max_speakers is not None:
                    arguments["max_speakers"] = options.max_speakers
            output = pipeline(str(audio_path), **arguments)
            if cancel_event.is_set():
                raise ProcessingCancelled()
            segments = [
                DiarizationSegment(
                    start=float(turn.start),
                    end=float(turn.end),
                    speaker=str(speaker),
                )
                for turn, _, speaker in output.itertracks(yield_label=True)
            ]
            segments.sort(key=lambda item: (item.start, item.end, item.speaker))
            if on_progress:
                on_progress(1.0)
            LOGGER.info(
                "Diarization complete: %d turns, %d speakers",
                len(segments),
                len({segment.speaker for segment in segments}),
            )
            agent_log(
                "diarization.py:diarize",
                "diarization complete",
                {
                    "segment_count": len(segments),
                    "speaker_count": len({segment.speaker for segment in segments}),
                    "sample_speakers": sorted({segment.speaker for segment in segments})[:5],
                },
                "H3",
            )
            return segments
        finally:
            if pipeline is not None:
                del pipeline
            self.model_manager.clear_cuda()

    def _load_pipeline(self, token: str, model_id: str | None = None, max_attempts: int = 5):
        from pyannote.audio import Pipeline

        pipeline_id = (model_id or MODEL_ID).strip() or MODEL_ID
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                agent_log(
                    "diarization.py:_load_pipeline",
                    "pipeline load attempt",
                    {"attempt": attempt, "model_id": pipeline_id},
                    "H6",
                )
                return Pipeline.from_pretrained(
                    pipeline_id,
                    use_auth_token=token,
                )
            except Exception as exc:
                last_error = exc
                agent_log(
                    "diarization.py:_load_pipeline",
                    "pipeline load attempt failed",
                    {
                        "attempt": attempt,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:300],
                    },
                    "H6",
                )
                if attempt == max_attempts or not is_retryable_download_error(exc):
                    raise
                delay_seconds = min(2**attempt, 30)
                LOGGER.warning(
                    "Retrying pyannote pipeline load in %d seconds (%s)",
                    delay_seconds,
                    exc,
                )
                time.sleep(delay_seconds)
        if last_error is not None:
            raise last_error
        raise RuntimeError("Pyannote pipeline load failed without an error.")
