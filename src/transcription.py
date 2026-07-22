import logging
import importlib
import os
import tempfile
import threading
import time
import warnings
from dataclasses import dataclass
from typing import Callable, Optional

import ffmpeg
import torch
import whisper
from tqdm import tqdm

WHISPER_TRANSCRIBE_MODULE = importlib.import_module("whisper.transcribe")

warnings.filterwarnings("ignore", category=FutureWarning, module="torch.serialization")

LOGGER = logging.getLogger("transcriber")

WHISPER_MODELS = ("tiny", "base", "small", "medium", "large")
DEFAULT_CHUNK_DURATION_SEC = 600


class TranscriptionCancelled(Exception):
    """Raised when transcription is cancelled by the user."""


@dataclass
class ProgressUpdate:
    phase: str
    progress: float
    chunk_index: int
    total_chunks: int
    elapsed_sec: float
    eta_sec: Optional[float]
    message: str


def _check_cancelled(cancel_event: threading.Event) -> None:
    if cancel_event.is_set():
        raise TranscriptionCancelled()


def _format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _compute_eta(elapsed_sec: float, progress: float) -> Optional[float]:
    if progress < 0.01:
        return None
    if progress >= 1.0:
        return 0.0
    return elapsed_sec / progress * (1.0 - progress)


def get_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def log_device_info(device: str) -> None:
    if device == "cuda":
        gpu_name = torch.cuda.get_device_name(0)
        cuda_version = torch.version.cuda or "unknown"
        LOGGER.info("Using GPU: %s (CUDA %s, fp16 enabled)", gpu_name, cuda_version)
    else:
        LOGGER.warning(
            "CUDA not available. Falling back to CPU transcription (slower). "
            "Install a CUDA-enabled PyTorch build for GPU acceleration."
        )


def probe_duration(video_path: str) -> float:
    try:
        probe = ffmpeg.probe(video_path)
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else str(exc)
        raise RuntimeError(f"Failed to probe video file: {stderr}") from exc

    duration = probe.get("format", {}).get("duration")
    if duration is None:
        raise RuntimeError("Could not determine video duration.")

    return float(duration)


def extract_audio_chunk(
    video_path: str,
    start_sec: float,
    duration_sec: float,
    output_path: str,
) -> None:
    try:
        (
            ffmpeg
            .input(video_path, ss=start_sec, t=duration_sec)
            .output(output_path, acodec="pcm_s16le", ar="16000", ac=1, vn=None)
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else str(exc)
        raise RuntimeError(f"Failed to extract audio chunk: {stderr}") from exc


def build_chunk_ranges(duration_sec: float, chunk_duration_sec: int) -> list[tuple[float, float]]:
    if duration_sec <= 0:
        return [(0.0, 0.0)]

    ranges = []
    start = 0.0
    while start < duration_sec:
        chunk_duration = min(chunk_duration_sec, duration_sec - start)
        ranges.append((start, chunk_duration))
        start += chunk_duration
    return ranges


class _ProgressTqdm(tqdm):
    def __init__(self, *args, **kwargs):
        self._cancel_event = kwargs.pop("cancel_event")
        self._on_frame_progress = kwargs.pop("on_frame_progress")
        super().__init__(*args, **kwargs)

    def update(self, n=1):
        if self._cancel_event.is_set():
            raise TranscriptionCancelled()
        result = super().update(n)
        if self.total:
            self._on_frame_progress(min(self.n / self.total, 1.0))
        return result


class WhisperTranscriber:
    def __init__(self):
        self._model_cache: dict[tuple[str, str], whisper.Whisper] = {}

    def get_model(self, model_size: str, device: str) -> whisper.Whisper:
        cache_key = (model_size, device)
        if cache_key not in self._model_cache:
            LOGGER.info("Loading Whisper model '%s' on %s...", model_size, device)
            self._model_cache[cache_key] = whisper.load_model(model_size, device=device)
            LOGGER.info("Whisper model '%s' loaded.", model_size)
        return self._model_cache[cache_key]

    def transcribe_chunk(
        self,
        audio_path: str,
        model_size: str,
        device: str,
        cancel_event: threading.Event,
        on_frame_progress: Callable[[float], None],
    ) -> str:
        model = self.get_model(model_size, device)
        use_fp16 = device == "cuda"
        original_tqdm = WHISPER_TRANSCRIBE_MODULE.tqdm.tqdm

        def make_progress_tqdm(*args, **kwargs):
            kwargs["cancel_event"] = cancel_event
            kwargs["on_frame_progress"] = on_frame_progress
            return _ProgressTqdm(*args, **kwargs)

        WHISPER_TRANSCRIBE_MODULE.tqdm.tqdm = make_progress_tqdm
        try:
            _check_cancelled(cancel_event)
            LOGGER.debug("Transcribing chunk audio: %s", os.path.basename(audio_path))
            result = model.transcribe(audio_path, fp16=use_fp16, verbose=False)
            return result["text"].strip()
        finally:
            WHISPER_TRANSCRIBE_MODULE.tqdm.tqdm = original_tqdm


_TRANSCRIBER = WhisperTranscriber()


def transcribe_video(
    video_path: str,
    model_size: str = "base",
    *,
    cancel_event: threading.Event,
    on_progress: Callable[[ProgressUpdate], None],
    chunk_duration_sec: int = DEFAULT_CHUNK_DURATION_SEC,
) -> str:
    if model_size not in WHISPER_MODELS:
        raise ValueError(f"Unsupported model size: {model_size}")

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if not video_path.lower().endswith(".mp4"):
        raise ValueError("Only .mp4 video files are supported.")

    start_time = time.time()
    temp_files: list[str] = []
    chunk_texts: list[str] = []

    def emit(
        phase: str,
        progress: float,
        chunk_index: int,
        total_chunks: int,
        message: str,
    ) -> None:
        elapsed_sec = time.time() - start_time
        on_progress(
            ProgressUpdate(
                phase=phase,
                progress=max(0.0, min(progress, 1.0)),
                chunk_index=chunk_index,
                total_chunks=total_chunks,
                elapsed_sec=elapsed_sec,
                eta_sec=_compute_eta(elapsed_sec, progress),
                message=message,
            )
        )

    try:
        _check_cancelled(cancel_event)
        emit("probing", 0.0, 0, 0, "Probing video duration...")
        LOGGER.info("Probing duration for %s", video_path)
        duration_sec = probe_duration(video_path)
        chunk_ranges = build_chunk_ranges(duration_sec, chunk_duration_sec)
        total_chunks = len(chunk_ranges)
        LOGGER.info(
            "Video duration: %s (%d chunks of up to %ds)",
            _format_duration(duration_sec),
            total_chunks,
            chunk_duration_sec,
        )

        _check_cancelled(cancel_event)
        device = get_device()
        log_device_info(device)
        emit("loading_model", 0.0, 0, total_chunks, f"Loading Whisper model '{model_size}'...")
        _TRANSCRIBER.get_model(model_size, device)

        for chunk_index, (start_sec, chunk_len) in enumerate(chunk_ranges, start=1):
            _check_cancelled(cancel_event)

            extract_progress = (chunk_index - 1) / total_chunks
            emit(
                "extracting",
                extract_progress,
                chunk_index,
                total_chunks,
                f"Extracting audio chunk {chunk_index}/{total_chunks}...",
            )
            LOGGER.info(
                "Extracting chunk %d/%d (start=%s, duration=%s)",
                chunk_index,
                total_chunks,
                _format_duration(start_sec),
                _format_duration(chunk_len),
            )

            fd, temp_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            temp_files.append(temp_path)
            extract_audio_chunk(video_path, start_sec, chunk_len, temp_path)

            frame_progress_holder = {"value": 0.0}

            def on_frame_progress(value: float, holder=frame_progress_holder) -> None:
                holder["value"] = value
                overall = ((chunk_index - 1) + value) / total_chunks
                emit(
                    "transcribing",
                    overall,
                    chunk_index,
                    total_chunks,
                    f"Transcribing chunk {chunk_index}/{total_chunks}...",
                )

            _check_cancelled(cancel_event)
            emit(
                "transcribing",
                (chunk_index - 1) / total_chunks,
                chunk_index,
                total_chunks,
                f"Transcribing chunk {chunk_index}/{total_chunks}...",
            )
            LOGGER.info("Transcribing chunk %d/%d", chunk_index, total_chunks)

            chunk_text = _TRANSCRIBER.transcribe_chunk(
                temp_path,
                model_size,
                device,
                cancel_event,
                on_frame_progress,
            )
            if chunk_text:
                chunk_texts.append(chunk_text)
                LOGGER.debug("Chunk %d transcript length: %d characters", chunk_index, len(chunk_text))

            try:
                os.remove(temp_path)
                temp_files.remove(temp_path)
            except OSError:
                LOGGER.warning("Could not delete temporary file: %s", temp_path)

        transcript = " ".join(chunk_texts).strip()
        emit("done", 1.0, total_chunks, total_chunks, "Transcription complete.")
        LOGGER.info(
            "Transcription complete (%d characters, elapsed %s).",
            len(transcript),
            _format_duration(time.time() - start_time),
        )
        return transcript

    except TranscriptionCancelled:
        LOGGER.info("Transcription cancelled by user.")
        raise
    finally:
        for temp_path in temp_files:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    LOGGER.warning("Could not delete temporary file: %s", temp_path)


def setup_file_logging(log_dir: str) -> str:
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "transcription.log")

    if not LOGGER.handlers:
        LOGGER.setLevel(logging.DEBUG)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )
        LOGGER.addHandler(file_handler)

    return log_path
